from django import template
from django.core.cache import cache
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
