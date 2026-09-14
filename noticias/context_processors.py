from django.core.cache import cache
from django.db.models import Count

from plataforma.identity import identidade_do_portal, identidade_vazia

from .models import Categoria, Contribuicao
from .utils import cache_key_portal


def site_context(request):
    portal = getattr(request, 'portal', None)
    extra = {
        'envios_pendentes': 0,
        'user_is_assinante': False,
        'is_platform_master': getattr(request, 'is_platform_master', False),
        'nav_categorias': [],
    }
    if portal is None:
        data = identidade_vazia()
        data.update(extra)
        return data

    data = identidade_do_portal(portal, request)
    nav_key = cache_key_portal('nav_categorias', portal)
    categorias = cache.get(nav_key)
    if categorias is None:
        categorias = list(
            Categoria.objects.annotate(num_noticias=Count('noticias')).order_by('nome')[:12]
        )
        cache.set(nav_key, categorias, 300)

    pendentes = 0
    is_assinante = False
    if request.user.is_authenticated:
        perfil = getattr(request.user, 'perfil', None)
        is_assinante = bool(perfil and perfil.is_assinante)
        if request.is_platform_master or getattr(request, 'membership', None):
            is_assinante = True
    if request.is_platform_master or (
        getattr(request, 'membership', None)
        and request.membership.papel in ('admin', 'moderador')
    ):
        pendentes = Contribuicao.objects.filter(status='pendente').count()

    data.update({
        'nav_categorias': categorias,
        'envios_pendentes': pendentes,
        'user_is_assinante': is_assinante,
        'is_platform_master': getattr(request, 'is_platform_master', False),
    })
    return data
