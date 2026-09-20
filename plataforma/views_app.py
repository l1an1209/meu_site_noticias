from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
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
    NoticiaForm, PortalOnboardingForm, SeoForm,
)
from plataforma.metrics import format_mb, storage_bytes_portal
from plataforma.models import ConversaAjuda, Membership, Portal
from plataforma.permissions import (
    PAPEIS_ANUNCIO, PAPEIS_CATEGORIA, PAPEIS_MODERACAO, PAPEIS_NOTICIA,
    has_portal_role, is_platform_master,
)
from plataforma.resolvers import resolve_portal_from_host
from plataforma.security import log_audit, safe_redirect
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

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not self.test_func():
                return self.handle_no_permission()
            if self._redirecionar_onboarding(request):
                return redirect(self.URL_ONBOARDING)
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
        return ctx


class AppHomeView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/dashboard.html'
    app_active = 'dashboard'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portal = self.request.portal
        noticias = Noticia.objects.all()
        hour = timezone.localtime().hour
        if hour < 12:
            saudacao = 'Bom dia'
        elif hour < 18:
            saudacao = 'Boa tarde'
        else:
            saudacao = 'Boa noite'
        ctx.update({
            'saudacao': saudacao,
            'total_noticias': noticias.count(),
            'total_categorias': Categoria.objects.count(),
            'total_envios': Contribuicao.objects.filter(status='pendente').count(),
            'total_videos': noticias.exclude(video='').exclude(video__isnull=True).count(),
            'total_fotos': noticias.exclude(imagem='').exclude(imagem__isnull=True).count(),
            'visualizacoes': noticias.aggregate(s=Sum('visualizacoes'))['s'] or 0,
            'recentes': list(noticias.order_by('-data_publicacao')[:6]),
            'storage_mb': format_mb(storage_bytes_portal(portal)),
            'plano_nome': portal.plano.nome if portal.plano else '—',
            'assinatura': portal.assinatura_atual(),
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
    success_url = reverse_lazy('app_noticias')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['portal'] = self.request.portal
        kwargs['extra_files'] = self.request.FILES.getlist('fotos_galeria')
        return kwargs

    def form_valid(self, form):
        form.instance.portal = self.request.portal
        form.instance.criado_por = self.request.user
        messages.success(self.request, 'Notícia publicada.')
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

    def get_queryset(self):
        return Categoria.objects.annotate(num=Count('noticias'))


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
        ctx['assinatura'] = portal.assinatura_atual()
        ctx['cliente_portal'] = portal.cliente
        ctx['host_previsto'] = portal.host_previsto
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
        if (
            request.user.is_authenticated
            and portal is not None
            and portal.setup_concluido
            and has_portal_role(request, Membership.PAPEL_ADMIN)
        ):
            return redirect('app_home')
        return super().dispatch(request, *args, **kwargs)

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
        messages.success(
            self.request,
            'Portal configurado. Este endereço não poderá ser alterado.',
        )
        return redirect(_url_app_no_novo_host(self.request, portal))
