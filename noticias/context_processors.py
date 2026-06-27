from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from .models import Categoria, Contribuicao


def site_context(request):
    categorias = cache.get('nav_categorias')
    if categorias is None:
        categorias = list(
            Categoria.objects.annotate(num_noticias=Count('noticias')).order_by('nome')[:12]
        )
        cache.set('nav_categorias', categorias, 300)

    pendentes = 0
    is_assinante = False
    if request.user.is_authenticated:
        perfil = getattr(request.user, 'perfil', None)
        is_assinante = bool(perfil and perfil.is_assinante) or request.user.is_staff
    if request.user.is_staff:
        pendentes = Contribuicao.objects.filter(status='pendente').count()

    return {
        'nav_categorias': categorias,
        'site_name': settings.SITE_NAME,
        'site_name_short': getattr(settings, 'SITE_NAME_SHORT', settings.SITE_CITY),
        'site_city': settings.SITE_CITY,
        'site_state': settings.SITE_STATE,
        'site_region': getattr(settings, 'SITE_REGION', ''),
        'site_slogan': getattr(settings, 'SITE_SLOGAN', 'Notícias em tempo real'),
        'site_tagline': settings.SITE_TAGLINE,
        'site_description': settings.SITE_DESCRIPTION,
        'site_logo': getattr(settings, 'SITE_LOGO', 'img/logo.png'),
        'site_favicon': getattr(settings, 'SITE_FAVICON', 'img/favicon.png'),
        'site_hero_image': getattr(settings, 'SITE_HERO_IMAGE', ''),
        'envios_pendentes': pendentes,
        'user_is_assinante': is_assinante,
    }
