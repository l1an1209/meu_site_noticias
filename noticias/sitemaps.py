from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Categoria, Noticia


class NoticiaSitemap(Sitemap):
    changefreq = 'hourly'
    priority = 0.8

    def items(self):
        return Noticia.objects.filter(exclusivo_assinantes=False).order_by('-data_publicacao')[:2000]

    def lastmod(self, obj):
        return obj.data_publicacao

    def location(self, obj):
        return f'/noticia/{obj.id}/'


class CategoriaSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.6

    def items(self):
        return Categoria.objects.all()

    def location(self, obj):
        return f'/categoria/{obj.slug}/'


class PaginasSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.5

    def items(self):
        return ['index', 'contribuir', 'videos', 'parceria', 'experiencia']

    def location(self, item):
        return reverse(item)


sitemaps = {
    'noticias': NoticiaSitemap,
    'categorias': CategoriaSitemap,
    'paginas': PaginasSitemap,
}
