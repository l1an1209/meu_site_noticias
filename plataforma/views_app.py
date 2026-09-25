from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView, DeleteView, FormView, ListView, TemplateView, UpdateView, View,
)

from noticias.models import Anuncio, Categoria, Contribuicao, Noticia, NoticiaImagem
from noticias.utils import limpar_cache_portal
from noticias.utils_noticia import criar_noticia_de_contribuicao
from plataforma.forms import (
    AnuncioForm, AparenciaForm, CategoriaForm, ConfigForm, EquipeForm,
    CadastroPortalForm, NoticiaForm, PortalOnboardingForm, SeoForm,
)
from plataforma.metrics import format_mb, storage_bytes_portal
from plataforma.models import ConversaAjuda, Membership, Plano, Portal
from plataforma.permissions import (
    PAPEIS_ANUNCIO, PAPEIS_CATEGORIA, PAPEIS_MODERACAO, PAPEIS_NOTICIA,
    has_portal_role, is_platform_master,
)
from plataforma.resolvers import resolve_portal_from_host
from plataforma.security import log_audit, safe_redirect
from plataforma.services.onboarding import provisionar_portal_gratuito
from plataforma.services.primeiro_acesso import (
    CATEGORIAS, COMPARTILHOU, IDENTIDADE, LIBERADAS, MARCA, VIU,
    adicionar_sugestao, destino_etapa, etapa_primeiro_acesso, garantir_categoria_padrao,
    noticia_guia, progresso, url_noticia_publica, url_whatsapp,
)
from plataforma.urls_portal import url_publica_portal
from plataforma.services.pos_login import (
    _port_suffix,
    app_url_for_portal,
    gravar_portal_sessao,
    portais_administraveis,
    portais_indisponiveis,
    tenant_host_for_portal,
)

User = get_user_model()


def _noticias_do_papel(request):
    qs = Noticia.objects.select_related('categoria')
    if request.user.is_superuser:
        return qs
    membership = getattr(request, 'membership', None)
    if membership and membership.papel == Membership.PAPEL_AUTOR:
        return qs.filter(criado_por=request.user)
    return qs


class AppAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('entrar')
    papeis_permitidos = ()
    raise_exception = False
    permite_onboarding_incompleto = False
    URL_ONBOARDING = 'app_comecar'

    def _url_onboarding_liberada(self, request):
        if getattr(self, 'permite_onboarding_incompleto', False):
            return True
        match = getattr(request, 'resolver_match', None)
        return getattr(match, 'url_name', None) == self.URL_ONBOARDING

    def _redirecionar_onboarding(self, request):
        if not request.user.is_authenticated:
            return False
        if is_platform_master(request.user):
            return False
        portal = getattr(request, 'portal', None)
        if portal is None or portal.setup_concluido:
            return False
        if self._url_onboarding_liberada(request):
            return False
        return True

    def _redirecionar_primeiro_acesso(self, request):
        if is_platform_master(request.user):
            return None
        portal = getattr(request, 'portal', None)
        etapa = etapa_primeiro_acesso(portal)
        if not etapa:
            return None
        match = getattr(request, 'resolver_match', None)
        nome = getattr(match, 'url_name', None)
        if nome in LIBERADAS:
            if nome == 'app_ativar' and etapa not in {'ver', 'compartilhar'}:
                return redirect(destino_etapa(etapa))
            return None
        return redirect(destino_etapa(etapa))

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not self.test_func():
                return self.handle_no_permission()
            if self._redirecionar_onboarding(request):
                return redirect(self.URL_ONBOARDING)
            destino = self._redirecionar_primeiro_acesso(request)
            if destino is not None:
                return destino
        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        if is_platform_master(self.request.user):
            return redirect('master_home')
        administraveis = list(portais_administraveis(self.request.user))
        if len(administraveis) > 1:
            return redirect('selecionar_portal')
        if len(administraveis) == 1:
            if resolve_portal_from_host(self.request.get_host()) is None:
                return redirect(app_url_for_portal(self.request, administraveis[0]))
            raise PermissionDenied(self.get_permission_denied_message())
        if portais_indisponiveis(self.request.user).exists():
            return redirect('acesso_portal_indisponivel')
        return redirect('pagina_vendas')

    def test_func(self):
        if getattr(self.request, 'portal', None) is None:
            return False
        if not self.papeis_permitidos:
            return has_portal_role(self.request)
        return has_portal_role(self.request, *self.papeis_permitidos)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['app_active'] = getattr(self, 'app_active', '')
        ctx['envios_pendentes_app'] = Contribuicao.objects.filter(status='pendente').count()
        ctx['ajuda_nao_lidas'] = (
            ConversaAjuda.objects.aggregate(n=Sum('nao_lidas_cliente'))['n'] or 0
        )
        portal = getattr(self.request, 'portal', None)
        etapa, itens = progresso(portal) if portal is not None else (None, ())
        ctx['primeiro_etapa'] = etapa
        ctx['primeiro_progresso'] = itens
        return ctx


def _identidade_configurada(portal):
    if portal.logo:
        return True
    return bool((portal.tagline or '').strip() or (portal.seo_title or '').strip())


def _guia_do_portal(portal, total_noticias):
    """Estado do painel a partir do portal e das notícias já existentes. Sem rascunho."""
    identidade = _identidade_configurada(portal)
    publicada = total_noticias > 0
    return {
        'mostrar_guia': not publicada,
        'identidade_ok': identidade,
        'publicada_ok': publicada,
        'proximo': 'noticia' if identidade else 'identidade',
    }


class AppAtivarView(AppAccessMixin, View):
    """Publicação, visualização e primeiro compartilhamento."""

    def get(self, request):
        etapa = etapa_primeiro_acesso(request.portal)
        if request.GET.get('pronto') and _tem_share(request.portal):
            ctx = self._ctx(request, 'compartilhar')
            ctx['pronto'] = True
            ctx['primeiro_etapa'] = None
            return render(request, 'plataforma/app/ativar.html', ctx)
        if etapa not in {'ver', 'compartilhar'}:
            return redirect(destino_etapa(etapa) if etapa else 'app_home')
        return render(request, 'plataforma/app/ativar.html', self._ctx(request, etapa))

    def post(self, request):
        etapa = etapa_primeiro_acesso(request.portal)
        acao = request.POST.get('acao')
        if etapa == 'ver' and acao == 'viu':
            log_audit(request, VIU, objeto='Portal', objeto_id=request.portal.pk)
            return redirect('app_ativar')
        if etapa == 'compartilhar' and acao == 'compartilhar':
            log_audit(request, COMPARTILHOU, objeto='Portal', objeto_id=request.portal.pk)
            if request.POST.get('canal') == 'copiar':
                messages.success(request, 'Link copiado!')
            messages.success(request, 'Portal pronto!')
            return redirect(reverse('app_ativar') + '?pronto=1')
        return redirect('app_ativar')

    def _ctx(self, request, etapa):
        noticia = noticia_guia(request.portal)
        link = url_noticia_publica(request.portal, noticia)
        _, itens = progresso(request.portal)
        pronto = _tem_share(request.portal)
        return {
            'app_active': 'ativar',
            'primeiro_etapa': None if pronto else etapa,
            'primeiro_progresso': itens,
            'noticia': noticia,
            'link_noticia': link,
            'link_whatsapp': url_whatsapp(request.portal, noticia),
            'portal_publico': url_publica_portal(request.portal),
            'pronto': pronto,
        }


def _tem_share(portal):
    from plataforma.services.primeiro_acesso import _tem
    return _tem(portal, COMPARTILHOU)


class AppHomeView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/dashboard.html'
    app_active = 'dashboard'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portal = self.request.portal
        noticias = Noticia.objects.all()
        total = noticias.count()
        hour = timezone.localtime().hour
        if hour < 12:
            saudacao = 'Bom dia'
        elif hour < 18:
            saudacao = 'Boa tarde'
        else:
            saudacao = 'Boa noite'
        ctx.update({
            'saudacao': saudacao,
            'total_noticias': total,
            'total_categorias': Categoria.objects.count(),
            'total_envios': Contribuicao.objects.filter(status='pendente').count(),
            'total_videos': noticias.exclude(video='').exclude(video__isnull=True).count(),
            'total_fotos': noticias.exclude(imagem='').exclude(imagem__isnull=True).count(),
            'visualizacoes': noticias.aggregate(s=Sum('visualizacoes'))['s'] or 0,
            'recentes': list(noticias.order_by('-data_publicacao')[:6]),
            'storage_mb': format_mb(storage_bytes_portal(portal)),
            'plano_nome': portal.plano.nome if portal.plano else '—',
            'assinatura': portal.assinatura_atual(),
            'guia': _guia_do_portal(portal, total),
            'status_portal': portal.get_status_display(),
        })
        return ctx


class AppNoticiaListView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/noticias_list.html'
    context_object_name = 'noticias'
    paginate_by = 15
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'noticias'

    def get_queryset(self):
        qs = _noticias_do_papel(self.request).order_by('-data_publicacao')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(titulo__icontains=q) | Q(conteudo__icontains=q))
        cat = self.request.GET.get('categoria')
        if cat:
            qs = qs.filter(categoria_id=cat)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categorias'] = Categoria.objects.all()
        ctx['q'] = self.request.GET.get('q', '')
        publicada = (self.request.GET.get('publicada') or '').strip()
        if publicada.isdigit():
            ctx['noticia_publicada'] = self.get_queryset().filter(pk=int(publicada)).first()
        return ctx


def _sync_galeria_noticia(request, noticia, extra_files):
    ids = [pk for pk in request.POST.getlist('remover_foto') if str(pk).isdigit()]
    if ids:
        noticia.fotos.filter(pk__in=ids).delete()
    ordem = noticia.fotos.count()
    for arquivo in extra_files:
        if not arquivo:
            continue
        foto = NoticiaImagem(noticia=noticia, ordem=ordem)
        foto.imagem = arquivo
        foto.save()
        ordem += 1


class AppNoticiaCreateView(AppAccessMixin, CreateView):
    template_name = 'plataforma/app/noticia_form.html'
    form_class = NoticiaForm
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'noticias'
    def get_success_url(self):
        if etapa_primeiro_acesso(self.request.portal) in {'noticia', 'ver'}:
            return reverse('app_ativar')
        return f"{reverse('app_noticias')}?publicada={self.object.pk}"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['portal'] = self.request.portal
        kwargs['extra_files'] = self.request.FILES.getlist('fotos_galeria')
        return kwargs

    def form_valid(self, form):
        form.instance.portal = self.request.portal
        form.instance.criado_por = self.request.user
        messages.success(self.request, 'Notícia publicada com sucesso.')
        limpar_cache_portal(self.request.portal)
        response = super().form_valid(form)
        _sync_galeria_noticia(self.request, form.instance, form.extra_files)
        log_audit(self.request, 'noticia_criar', objeto='Noticia', objeto_id=form.instance.pk)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Nova notícia'
        return ctx


class AppNoticiaUpdateView(AppAccessMixin, UpdateView):
    template_name = 'plataforma/app/noticia_form.html'
    form_class = NoticiaForm
    model = Noticia
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'noticias'
    success_url = reverse_lazy('app_noticias')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['portal'] = self.request.portal
        kwargs['extra_files'] = self.request.FILES.getlist('fotos_galeria')
        return kwargs

    def get_queryset(self):
        return _noticias_do_papel(self.request)

    def form_valid(self, form):
        messages.success(self.request, 'Notícia atualizada.')
        limpar_cache_portal(self.request.portal)
        log_audit(self.request, 'noticia_editar', objeto='Noticia', objeto_id=form.instance.pk)
        response = super().form_valid(form)
        _sync_galeria_noticia(self.request, form.instance, form.extra_files)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Editar notícia'
        return ctx


class AppNoticiaDeleteView(AppAccessMixin, DeleteView):
    model = Noticia
    template_name = 'plataforma/app/confirm_delete.html'
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'noticias'
    success_url = reverse_lazy('app_noticias')

    def get_queryset(self):
        return _noticias_do_papel(self.request)

    def form_valid(self, form):
        pk = self.get_object().pk
        messages.warning(self.request, 'Notícia excluída.')
        limpar_cache_portal(self.request.portal)
        log_audit(self.request, 'noticia_excluir', objeto='Noticia', objeto_id=pk)
        return super().form_valid(form)


class AppCategoriaListView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/categorias.html'
    model = Categoria
    context_object_name = 'categorias'
    papeis_permitidos = tuple(PAPEIS_CATEGORIA)
    app_active = 'categorias'

    def get(self, request, *args, **kwargs):
        if etapa_primeiro_acesso(request.portal) == 'categorias':
            garantir_categoria_padrao(request.portal)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if etapa_primeiro_acesso(request.portal) != 'categorias':
            return redirect('app_categorias')
        if request.POST.get('sugestao'):
            adicionar_sugestao(request.portal, request.POST.get('sugestao'))
            return redirect('app_categorias')
        if not Categoria.all_objects.filter(portal=request.portal).exists():
            garantir_categoria_padrao(request.portal)
        log_audit(request, CATEGORIAS, objeto='Portal', objeto_id=request.portal.pk)
        messages.success(request, 'Categorias prontas.')
        return redirect('app_noticia_nova')

    def get_queryset(self):
        return Categoria.objects.annotate(num=Count('noticias'))

    def get_context_data(self, **kwargs):
        from plataforma.services.primeiro_acesso import SUGESTOES
        ctx = super().get_context_data(**kwargs)
        existentes = set(Categoria.all_objects.filter(portal=self.request.portal).values_list('slug', flat=True))
        ctx['sugestoes'] = [par for par in SUGESTOES if par[1] not in existentes]
        return ctx


class AppCategoriaCreateView(AppAccessMixin, CreateView):
    template_name = 'plataforma/app/form.html'
    form_class = CategoriaForm
    papeis_permitidos = tuple(PAPEIS_CATEGORIA)
    app_active = 'categorias'
    success_url = reverse_lazy('app_categorias')

    def form_valid(self, form):
        form.instance.portal = self.request.portal
        messages.success(self.request, 'Categoria criada.')
        limpar_cache_portal(self.request.portal)
        response = super().form_valid(form)
        log_audit(self.request, 'categoria_criar', objeto='Categoria', objeto_id=form.instance.pk)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Nova categoria'
        return ctx


class AppCategoriaUpdateView(AppAccessMixin, UpdateView):
    template_name = 'plataforma/app/form.html'
    form_class = CategoriaForm
    model = Categoria
    papeis_permitidos = tuple(PAPEIS_CATEGORIA)
    app_active = 'categorias'
    success_url = reverse_lazy('app_categorias')

    def form_valid(self, form):
        messages.success(self.request, 'Categoria atualizada.')
        limpar_cache_portal(self.request.portal)
        log_audit(self.request, 'categoria_editar', objeto='Categoria', objeto_id=form.instance.pk)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Editar categoria'
        return ctx


class AppCategoriaDeleteView(AppAccessMixin, DeleteView):
    model = Categoria
    template_name = 'plataforma/app/confirm_delete.html'
    papeis_permitidos = tuple(PAPEIS_CATEGORIA)
    success_url = reverse_lazy('app_categorias')
    app_active = 'categorias'


class AppFotosView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/midia.html'
    paginate_by = 24
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'fotos'
    context_object_name = 'noticias'

    def get_queryset(self):
        return (
            _noticias_do_papel(self.request)
            .exclude(imagem='')
            .exclude(imagem__isnull=True)
            .order_by('-data_publicacao')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['midia_tipo'] = 'fotos'
        ctx['page_title'] = 'Fotos'
        return ctx


class AppVideosView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/midia.html'
    paginate_by = 24
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'videos'
    context_object_name = 'noticias'

    def get_queryset(self):
        return (
            _noticias_do_papel(self.request)
            .exclude(video='')
            .exclude(video__isnull=True)
            .order_by('-data_publicacao')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['midia_tipo'] = 'videos'
        ctx['page_title'] = 'Vídeos'
        return ctx


class AppGaleriaView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/galeria.html'
    paginate_by = 36
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'galeria'
    context_object_name = 'fotos'

    def get_queryset(self):
        return NoticiaImagem.objects.filter(
            noticia__portal=self.request.portal,
        ).select_related('noticia').order_by('-id')


class AppEnviosView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/envios.html'
    paginate_by = 15
    papeis_permitidos = tuple(PAPEIS_MODERACAO)
    app_active = 'envios'
    context_object_name = 'envios'

    def get_queryset(self):
        status = self.request.GET.get('status', 'pendente')
        return Contribuicao.objects.filter(status=status).select_related('categoria').prefetch_related('fotos')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtro_status'] = self.request.GET.get('status', 'pendente')
        ctx['contagem_pendente'] = Contribuicao.objects.filter(status='pendente').count()
        ctx['contagem_aprovado'] = Contribuicao.objects.filter(status='aprovado').count()
        ctx['contagem_rejeitado'] = Contribuicao.objects.filter(status='rejeitado').count()
        return ctx


class AppAprovarEnvioView(AppAccessMixin, View):
    papeis_permitidos = tuple(PAPEIS_MODERACAO)

    def post(self, request, pk):
        contrib = get_object_or_404(Contribuicao, pk=pk, status='pendente')
        criar_noticia_de_contribuicao(contrib)
        contrib.status = 'aprovado'
        contrib.save(update_fields=['status'])
        limpar_cache_portal(request.portal)
        log_audit(request, 'envio_aprovar', objeto='Contribuicao', objeto_id=pk)
        messages.success(request, f'"{contrib.titulo}" publicado no portal.')
        return safe_redirect(request, request.POST.get('next'), 'app_envios')


class AppRejeitarEnvioView(AppAccessMixin, View):
    papeis_permitidos = tuple(PAPEIS_MODERACAO)

    def post(self, request, pk):
        contrib = get_object_or_404(Contribuicao, pk=pk, status='pendente')
        contrib.status = 'rejeitado'
        contrib.save(update_fields=['status'])
        log_audit(request, 'envio_rejeitar', objeto='Contribuicao', objeto_id=pk)
        messages.warning(request, f'Envio "{contrib.titulo}" não publicado.')
        return redirect('app_envios')


class AppAutoresView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/autores.html'
    papeis_permitidos = tuple(PAPEIS_NOTICIA)
    app_active = 'autores'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['autores'] = (
            Noticia.objects.values('autor')
            .annotate(total=Count('id'), views=Sum('visualizacoes'))
            .order_by('-total')
        )
        return ctx


class AppUsuariosView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/usuarios.html'
    papeis_permitidos = (Membership.PAPEL_ADMIN,)
    app_active = 'usuarios'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['membros'] = Membership.objects.filter(
            portal=self.request.portal,
        ).select_related('usuario')
        ctx['form'] = EquipeForm()
        return ctx


class AppUsuarioCreateView(AppAccessMixin, FormView):
    template_name = 'plataforma/app/form.html'
    form_class = EquipeForm
    papeis_permitidos = (Membership.PAPEL_ADMIN,)
    app_active = 'usuarios'
    success_url = reverse_lazy('app_usuarios')

    def form_valid(self, form):
        user = User.objects.create_user(
            username=form.cleaned_data['username'],
            email=form.cleaned_data.get('email') or '',
            password=form.cleaned_data['password'],
        )
        Membership.objects.create(
            usuario=user,
            portal=self.request.portal,
            papel=form.cleaned_data['papel'],
            ativo=True,
        )
        log_audit(self.request, 'usuario_criar', objeto='User', objeto_id=user.pk, detalhes={'papel': form.cleaned_data['papel']})
        messages.success(self.request, 'Membro adicionado à equipe.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Novo membro da equipe'
        return ctx


class AppPublicidadeView(AppAccessMixin, ListView):
    template_name = 'plataforma/app/publicidade.html'
    model = Anuncio
    context_object_name = 'anuncios'
    papeis_permitidos = tuple(PAPEIS_ANUNCIO)
    app_active = 'publicidade'


class AppAnuncioUpdateView(AppAccessMixin, UpdateView):
    template_name = 'plataforma/app/form.html'
    form_class = AnuncioForm
    model = Anuncio
    papeis_permitidos = tuple(PAPEIS_ANUNCIO)
    app_active = 'publicidade'
    success_url = reverse_lazy('app_publicidade')

    def form_valid(self, form):
        form.instance.portal = self.request.portal
        messages.success(self.request, 'Espaço publicitário atualizado.')
        limpar_cache_portal(self.request.portal)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Editar anúncio'
        return ctx


class AppAnuncioCreateView(AppAccessMixin, CreateView):
    template_name = 'plataforma/app/form.html'
    form_class = AnuncioForm
    papeis_permitidos = tuple(PAPEIS_ANUNCIO)
    app_active = 'publicidade'
    success_url = reverse_lazy('app_publicidade')

    def form_valid(self, form):
        form.instance.portal = self.request.portal
        messages.success(self.request, 'Anúncio criado.')
        limpar_cache_portal(self.request.portal)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Novo anúncio'
        return ctx


class AppPortalFormMixin(AppAccessMixin):
    papeis_permitidos = (Membership.PAPEL_ADMIN,)
    model = Portal

    def get_object(self, queryset=None):
        return self.request.portal

    def form_valid(self, form):
        messages.success(self.request, 'Alterações salvas. Elas valem só para este portal.')
        limpar_cache_portal(self.request.portal)
        log_audit(self.request, 'portal_atualizar', objeto='Portal', objeto_id=self.request.portal.pk)
        return super().form_valid(form)


class AppAparenciaView(AppPortalFormMixin, UpdateView):
    template_name = 'plataforma/app/aparencia.html'
    form_class = AparenciaForm
    app_active = 'aparencia'
    success_url = reverse_lazy('app_aparencia')

    def form_valid(self, form):
        if etapa_primeiro_acesso(self.request.portal) == 'identidade' and (form.cleaned_data.get('nome') or '').strip():
            self.object = form.save()
            limpar_cache_portal(self.request.portal)
            log_audit(self.request, 'portal_atualizar', objeto='Portal', objeto_id=self.request.portal.pk)
            log_audit(self.request, IDENTIDADE, objeto='Portal', objeto_id=self.request.portal.pk)
            messages.success(self.request, 'Identidade configurada.')
            return redirect('app_categorias')
        return super().form_valid(form)


class AppSeoView(AppPortalFormMixin, UpdateView):
    template_name = 'plataforma/app/form.html'
    form_class = SeoForm
    app_active = 'seo'
    success_url = reverse_lazy('app_seo')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'SEO do portal'
        return ctx


class AppConfigView(AppPortalFormMixin, UpdateView):
    template_name = 'plataforma/app/form.html'
    form_class = ConfigForm
    app_active = 'config'
    success_url = reverse_lazy('app_config')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'Configurações'
        return ctx


class AppAssinaturaView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/assinatura.html'
    papeis_permitidos = (Membership.PAPEL_ADMIN,)
    app_active = 'assinatura'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portal = self.request.portal
        assinatura = portal.assinatura_atual()
        ctx['assinatura'] = assinatura
        ctx['cliente_portal'] = portal.cliente
        ctx['host_previsto'] = portal.host_previsto
        atual = portal.plano
        ctx['plano_atual'] = atual
        ctx['planos_upgrade'] = Plano.objects.filter(ativo=True, preco_mensal__gt=0).order_by('ordem', 'preco_mensal')
        ctx['pode_upgrade'] = atual is None or atual.e_gratuito
        return ctx


def _url_app_no_novo_host(request, portal):
    """Redirect absoluto para /app/ no host do slug recém-salvo."""
    gravar_portal_sessao(request, portal)
    scheme = 'https' if request.is_secure() else 'http'
    host = tenant_host_for_portal(request, portal)
    return f'{scheme}://{host}{_port_suffix(request)}{reverse("app_home")}'


class AppComecarView(AppAccessMixin, FormView):
    """Configuração única de nome e slug. Sem gate global nesta fase."""

    template_name = 'plataforma/app/comecar.html'
    form_class = PortalOnboardingForm
    papeis_permitidos = (Membership.PAPEL_ADMIN,)
    app_active = 'comecar'
    permite_onboarding_incompleto = True

    def dispatch(self, request, *args, **kwargs):
        portal = getattr(request, 'portal', None)
        if portal is None:
            return self._dispatch_cadastro(request)
        if (
            request.user.is_authenticated
            and portal.setup_concluido
            and has_portal_role(request, Membership.PAPEL_ADMIN)
        ):
            return redirect('app_home')
        return super().dispatch(request, *args, **kwargs)

    def _dispatch_cadastro(self, request):
        if request.user.is_authenticated:
            destinos = list(portais_administraveis(request.user)[:1])
            if destinos:
                return redirect(app_url_for_portal(request, destinos[0]))
        usuario = request.user if request.user.is_authenticated else None
        if request.method == 'POST':
            form = CadastroPortalForm(request.POST, usuario=usuario)
            if form.is_valid():
                return self._concluir_cadastro(request, form)
        else:
            form = CadastroPortalForm(usuario=usuario)
        return render(request, 'plataforma/app/comecar_gratis.html', {
            'form': form,
            'planos': list(form.planos.values()),
            'tenant_base_domain': getattr(settings, 'TENANT_BASE_DOMAIN', 'portalnoticias.com.br'),
            'mostrar_formulario': request.method == 'POST' or bool(form.errors),
        })

    def _concluir_cadastro(self, request, form):
        plano = form.plano_escolhido
        if plano is None or not plano.e_gratuito:
            codigo = plano.codigo if plano else 'basico'
            return redirect('pagina_checkout_plano', codigo=codigo)
        dados = form.cleaned_data
        usuario = request.user if request.user.is_authenticated else None
        resultado = provisionar_portal_gratuito(
            nome=dados['nome'],
            email=dados['email'],
            slug=dados['slug'],
            cidade=dados.get('cidade') or '',
            estado=dados.get('estado') or '',
            senha=dados.get('senha') or '',
            usuario=usuario,
            request=request,
        )
        user = resultado['usuario']
        if not request.user.is_authenticated:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Portal criado. Você já pode publicar.')
        return redirect(_url_app_no_novo_host(request, resultado['portal']))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['portal'] = self.request.portal
        return kwargs

    def get_initial(self):
        portal = self.request.portal
        nome = portal.nome or ''
        slug = portal.slug or ''
        if nome.strip() == 'Portal em configuração':
            nome = ''
        if slug.startswith('setup-'):
            slug = ''
        return {
            'nome': nome,
            'slug': slug,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant_base_domain'] = getattr(
            settings, 'TENANT_BASE_DOMAIN', 'portalnoticias.com.br',
        )
        return ctx

    def form_valid(self, form):
        portal = self.request.portal
        if portal.setup_concluido:
            return redirect('app_home')
        portal.nome = form.cleaned_data['nome']
        portal.slug = form.cleaned_data['slug']
        portal.setup_concluido = True
        try:
            with transaction.atomic():
                portal.save(update_fields=['nome', 'slug', 'setup_concluido'])
        except IntegrityError:
            portal.refresh_from_db()
            form.add_error(
                'slug',
                'Este subdomínio acabou de ser ocupado. Escolha outro.',
            )
            return self.form_invalid(form)
        limpar_cache_portal(portal)
        log_audit(
            self.request,
            'portal_onboarding',
            objeto='Portal',
            objeto_id=portal.pk,
            detalhes={'slug': portal.slug},
        )
        log_audit(self.request, MARCA, objeto='Portal', objeto_id=portal.pk, portal=portal)
        messages.success(
            self.request,
            'Portal configurado. Este endereço não poderá ser alterado.',
        )
        return redirect(_url_app_no_novo_host(self.request, portal))
