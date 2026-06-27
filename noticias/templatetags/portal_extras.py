from django import template
from django.core.cache import cache
from django.conf import settings
from ..models import Anuncio

register = template.Library()


@register.simple_tag(takes_context=True)
def query_string(context, page=None, **kwargs):
    request = context['request']
    params = request.GET.copy()
    if page is not None:
        if page == 1:
            params.pop('page', None)
        else:
            params['page'] = page
    for key, value in kwargs.items():
        if value in (None, '', 0, '0'):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.inclusion_tag('noticias/partials/ad_slot.html')
def ad_slot(slot):
    cache_key = f'anuncio_{slot}'
    anuncio = cache.get(cache_key)
    if anuncio is None:
        try:
            anuncio = Anuncio.objects.get(slot=slot)
        except Anuncio.DoesNotExist:
            anuncio = None
        cache.set(cache_key, anuncio, 120)
    return {'anuncio': anuncio, 'slot': slot}


@register.simple_tag
def noticia_capa(noticia):
    """URL da capa: foto real ou imagem editorial de fallback."""
    if noticia.imagem:
        return noticia.imagem.url
    slug = ''
    if noticia.categoria and noticia.categoria.slug:
        slug = noticia.categoria.slug.lower()
    for key, url in _placeholder_map().items():
        if key in slug:
            return url
    return _placeholder_map()['default']


def _placeholder_map():
    return {
        'default': getattr(
            settings, 'PLACEHOLDER_DEFAULT',
            'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=900&q=80',
        ),
        'polic': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&q=80',
        'polit': 'https://images.unsplash.com/photo-1529107386315-e1a2cc712a89?w=900&q=80',
        'tecno': 'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&q=80',
        'social': 'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=900&q=80',
        'ajuda': 'https://images.unsplash.com/photo-1469571486292-0fba78523826?w=900&q=80',
        'esport': 'https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=900&q=80',
        'cidade': 'https://images.unsplash.com/photo-1449824913935-59a10b8d2000?w=900&q=80',
    }
