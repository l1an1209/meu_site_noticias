from django.core.cache import cache


def limpar_cache_portal():
    cache.delete_many([
        'categorias_sidebar', 'nav_categorias', 'noticias_populares',
        'noticias_destaques', 'anuncio_top', 'anuncio_sidebar', 'anuncio_article',
    ])
