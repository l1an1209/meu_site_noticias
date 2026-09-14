from django.core.cache import cache

from plataforma.context import get_current_portal


def cache_key_portal(nome, portal=None):
    portal = portal if portal is not None else get_current_portal()
    pid = getattr(portal, 'pk', None) or 'none'
    return f'tenant:{pid}:{nome}'


def limpar_cache_portal(portal=None):
    portal = portal if portal is not None else get_current_portal()
    keys = [
        'categorias_sidebar', 'nav_categorias', 'noticias_populares',
        'noticias_destaques', 'noticias_destaques_v2',
        'anuncio_top', 'anuncio_sidebar', 'anuncio_article',
        'anuncio_feed', 'anuncio_mobile',
    ]
    cache.delete_many([cache_key_portal(k, portal) for k in keys])
