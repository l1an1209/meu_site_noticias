from django.conf import settings
from django.views.generic import ListView, DetailView, CreateView
from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.core.cache import cache
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Noticia, Categoria, Contribuicao, Curtida, Comentario
from .forms import ContribuicaoForm, ComentarioForm
from .utils import limpar_cache_portal
from .utils_noticia import criar_noticia_de_contribuicao


class NoticiasBaseMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categorias = cache.get('categorias_sidebar')
        if not categorias:
            categorias = list(
                Categoria.objects.annotate(num_noticias=Count('noticias')).order_by('nome')
            )
            cache.set('categorias_sidebar', categorias, 300)

        populares = cache.get('noticias_populares')
        if not populares:
            populares = list(Noticia.objects.order_by('-visualizacoes')[:5])
            cache.set('noticias_populares', populares, 300)

        destaques = cache.get('noticias_destaques_v2')
        if not destaques:
            destaques = list(
                Noticia.objects.filter(destaque=True).order_by('-data_publicacao')[:5]
            )
            if len(destaques) < 5:
                ids = [n.id for n in destaques]
                extras = list(
                    Noticia.objects.exclude(id__in=ids).order_by('-data_publicacao')[: 5 - len(destaques)]
                )
                destaques = destaques + extras
            cache.set('noticias_destaques_v2', destaques, 300)

        context['categorias'] = categorias
        context['noticias_populares'] = populares
        context['noticias_destaques'] = destaques
        context['manchete_urgente'] = destaques[0] if destaques else None
        context['ordenacao_atual'] = self.request.GET.get('ordenacao', '-data_publicacao')
        context['busca'] = self.request.GET.get('q', '').strip()
        context['total_noticias'] = Noticia.objects.count()
        return context

    def _usuario_ve_exclusivo(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        perfil = getattr(user, 'perfil', None)
        return bool(perfil and perfil.is_assinante)


class NoticiaListView(NoticiasBaseMixin, ListView):
    model = Noticia
    template_name = 'noticias/index.html'
    context_object_name = 'noticias'
    paginate_by = 8

    def get_queryset(self):
        ordenacao = self.request.GET.get('ordenacao', '-data_publicacao')
        ordenacoes_validas = {
            '-data_publicacao': '-data_publicacao',
            'data_publicacao': 'data_publicacao',
            '-visualizacoes': '-visualizacoes',
        }
        ordenacao = ordenacoes_validas.get(ordenacao, '-data_publicacao')
        queryset = Noticia.objects.select_related('categoria').order_by(ordenacao)

        categoria_id = self.request.GET.get('categoria')
        if categoria_id and categoria_id != '0':
            queryset = queryset.filter(categoria_id=categoria_id)

        busca = self.request.GET.get('q', '').strip()
        if busca:
            queryset = queryset.filter(titulo__icontains=busca) | queryset.filter(
                conteudo__icontains=busca
            )
        if not self._usuario_ve_exclusivo():
            queryset = queryset.filter(exclusivo_assinantes=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categoria_id = self.request.GET.get('categoria')
        try:
            context['categoria_selecionada'] = int(categoria_id) if categoria_id else 0
        except (TypeError, ValueError):
            context['categoria_selecionada'] = 0
        return context


class NoticiaDetailView(NoticiasBaseMixin, DetailView):
    model = Noticia
    template_name = 'noticias/detalhe.html'
    context_object_name = 'noticia'
    pk_url_kwarg = 'id'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        Noticia.objects.filter(pk=self.object.pk).update(visualizacoes=F('visualizacoes') + 1)
        self.object.refresh_from_db(fields=['visualizacoes'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        noticia = self.object
        perfil = getattr(self.request.user, 'perfil', None) if self.request.user.is_authenticated else None
        context['pode_ver_exclusivo'] = (
            not noticia.exclusivo_assinantes
            or self.request.user.is_staff
            or (perfil and perfil.is_assinante)
        )
        context['noticias_relacionadas'] = (
            Noticia.objects.filter(categoria=noticia.categoria)
            .exclude(id=noticia.id)
            .order_by('-data_publicacao')[:3]
        )
        context['comentarios'] = (
            Comentario.objects.filter(noticia=noticia, ativo=True)
            .select_related('usuario', 'usuario__perfil')[:50]
        )
        context['comentario_form'] = ComentarioForm()
        context['total_curtidas'] = noticia.curtidas.count()
        context['usuario_curtiu'] = (
            self.request.user.is_authenticated
            and Curtida.objects.filter(noticia=noticia, usuario=self.request.user).exists()
        )
        context['share_url'] = self.request.build_absolute_uri()
        context['share_text'] = noticia.titulo
        return context


class NoticiaPorCategoriaListView(NoticiasBaseMixin, ListView):
    model = Noticia
    template_name = 'noticias/index.html'
    context_object_name = 'noticias'
    paginate_by = 8

    def get_queryset(self):
        self.categoria = get_object_or_404(Categoria, slug=self.kwargs['slug'])
        qs = Noticia.objects.filter(categoria=self.categoria).select_related(
            'categoria'
        ).order_by('-data_publicacao')
        if not self._usuario_ve_exclusivo():
            qs = qs.filter(exclusivo_assinantes=False)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categoria'] = self.categoria
        context['categoria_selecionada'] = self.categoria.id
        return context


class ContribuicaoCreateView(CreateView):
    model = Contribuicao
    form_class = ContribuicaoForm
    template_name = 'noticias/contribuir.html'
    success_url = reverse_lazy('contribuir')

    def form_valid(self, form):
        form.instance.status = 'pendente'
        messages.success(
            self.request,
            f'Envio recebido! Sua publicação está na fila de análise do {settings.SITE_NAME}. '
            f'A equipe de {settings.SITE_CITY} revisa em breve — obrigado por participar.',
        )
        limpar_cache_portal()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias'] = Categoria.objects.order_by('nome')
        return context


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class PainelModeracaoView(StaffRequiredMixin, ListView):
    """Painel simples para você ver envios — além do /admin/"""
    model = Contribuicao
    template_name = 'noticias/painel.html'
    context_object_name = 'envios'
    paginate_by = 15
    login_url = reverse_lazy('entrar')

    def get_queryset(self):
        status = self.request.GET.get('status', 'pendente')
        return Contribuicao.objects.filter(status=status).select_related('categoria')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filtro_status'] = self.request.GET.get('status', 'pendente')
        context['contagem_pendente'] = Contribuicao.objects.filter(status='pendente').count()
        context['contagem_aprovado'] = Contribuicao.objects.filter(status='aprovado').count()
        context['contagem_rejeitado'] = Contribuicao.objects.filter(status='rejeitado').count()
        return context


class AprovarEnvioView(StaffRequiredMixin, View):
    login_url = reverse_lazy('entrar')

    def post(self, request, pk):
        contrib = get_object_or_404(Contribuicao, pk=pk, status='pendente')
        criar_noticia_de_contribuicao(contrib)
        contrib.status = 'aprovado'
        contrib.save(update_fields=['status'])
        limpar_cache_portal()
        messages.success(request, f'"{contrib.titulo}" publicado no portal!')
        return redirect('painel')


class RejeitarEnvioView(StaffRequiredMixin, View):
    login_url = reverse_lazy('entrar')

    def post(self, request, pk):
        contrib = get_object_or_404(Contribuicao, pk=pk, status='pendente')
        contrib.status = 'rejeitado'
        contrib.save(update_fields=['status'])
        messages.warning(request, f'Envio "{contrib.titulo}" marcado como não publicado.')
        return redirect('painel')
