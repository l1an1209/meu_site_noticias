from django.views.generic import ListView, DetailView
from django.shortcuts import get_object_or_404
from django.db.models import Count
from .models import Noticia, Categoria


class NoticiaListView(ListView):
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

        context['categorias'] = Categoria.objects.annotate(num_noticias=Count('noticia'))
        context['noticias_populares'] = Noticia.objects.order_by('-visualizacoes')[:5]
        context['categoria_selecionada'] = int(categoria_id) if categoria_id else 0

        return context


class NoticiaDetailView(DetailView):
    model = Noticia
    template_name = 'noticias/detalhe.html'
    context_object_name = 'noticia'
    pk_url_kwarg = 'id'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.visualizacoes += 1
        self.object.save(update_fields=['visualizacoes'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        noticia = self.object
        context['noticias_relacionadas'] = Noticia.objects.filter(
            categoria=noticia.categoria
        ).exclude(id=noticia.id).order_by('-data_publicacao')[:3]

        context['categorias'] = Categoria.objects.annotate(num_noticias=Count('noticia'))
        context['noticias_populares'] = Noticia.objects.order_by('-visualizacoes')[:5]

        return context


class NoticiaPorCategoriaListView(ListView):
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
        context['categorias'] = Categoria.objects.annotate(num_noticias=Count('noticia'))
        context['noticias_populares'] = Noticia.objects.order_by('-visualizacoes')[:5]
        context['categoria_selecionada'] = self.categoria.id
        return context
