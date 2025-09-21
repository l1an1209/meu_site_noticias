from django.views.generic import ListView, DetailView
from django.shortcuts import get_object_or_404
from django.db.models import Count, F
from django.core.cache import cache
from .models import Noticia, Categoria


# 🔹 Mixin para centralizar categorias e populares
class NoticiasBaseMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categorias = cache.get('categorias')
        if not categorias:
            categorias = Categoria.objects.annotate(num_noticias=Count('noticia'))
            cache.set('categorias', categorias, 300)  # 5 min de cache

        populares = cache.get('noticias_populares')
        if not populares:
            populares = Noticia.objects.order_by('-visualizacoes')[:5]
            cache.set('noticias_populares', populares, 300)

        context['categorias'] = categorias
        context['noticias_populares'] = populares
        return context


# 🔹 Lista de notícias (com filtro e ordenação)
class NoticiaListView(NoticiasBaseMixin, ListView):
    model = Noticia
    template_name = 'noticias/index.html'
    context_object_name = 'noticias'
    paginate_by = 10

    def get_queryset(self):
        categoria_id = self.request.GET.get('categoria')
        ordenacao = self.request.GET.get('ordenacao', '-data_publicacao')

        queryset = Noticia.objects.all().order_by(ordenacao)

        if categoria_id and categoria_id != '0':
            queryset = queryset.filter(categoria_id=categoria_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categoria_id = self.request.GET.get('categoria')
        context['categoria_selecionada'] = int(categoria_id) if categoria_id else 0
        return context


# 🔹 Detalhe da notícia (com slug para SEO)
class NoticiaDetailView(NoticiasBaseMixin, DetailView):
    model = Noticia
    template_name = 'noticias/detalhe.html'
    context_object_name = 'noticia'
    slug_url_kwarg = 'slug'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Incremento seguro usando F()
        Noticia.objects.filter(pk=self.object.pk).update(visualizacoes=F('visualizacoes') + 1)
        self.object.refresh_from_db(fields=['visualizacoes'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        noticia = self.object
        context['noticias_relacionadas'] = Noticia.objects.filter(
            categoria=noticia.categoria
        ).exclude(id=noticia.id).order_by('-data_publicacao')[:3]
        return context


# 🔹 Lista de notícias por categoria
class NoticiaPorCategoriaListView(NoticiasBaseMixin, ListView):
    model = Noticia
    template_name = 'noticias/index.html'
    context_object_name = 'noticias'
    paginate_by = 10

    def get_queryset(self):
        self.categoria = get_object_or_404(Categoria, slug=self.kwargs['slug'])
        return Noticia.objects.filter(categoria=self.categoria).order_by('-data_publicacao')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categoria'] = self.categoria
        context['categoria_selecionada'] = self.categoria.id
        return context
