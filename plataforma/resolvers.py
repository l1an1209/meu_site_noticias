from django.conf import settings

from .models import Portal

PLATFORM_LABELS = {
    'www', 'admin', 'plataforma', 'localhost', 'testserver', '127',
}


def _host_only(host):
    return (host or '').split(':')[0].lower().strip()


def is_local_or_platform_host(host):
    host = _host_only(host)
    extra = {h.lower() for h in getattr(settings, 'PLATFORM_HOSTS', ())}
    if host in extra or host in {'localhost', '127.0.0.1', 'testserver'}:
        return True
    label = host.split('.')[0]
    return label in PLATFORM_LABELS


def resolve_portal_from_host(host):
    """Identifica o portal pelo Host. None = sem tenant (plataforma ou host desconhecido)."""
    host = _host_only(host)
    if not host:
        return None

    custom = (
        Portal.objects.exclude(custom_domain='')
        .filter(custom_domain__iexact=host)
        .first()
    )
    if custom:
        return custom

    if is_local_or_platform_host(host):
        return None

    slug = host.split('.')[0]
    if not slug or slug in PLATFORM_LABELS:
        return None
    return Portal.objects.filter(slug=slug).first()


def resolve_portal_for_request(request):
    """
    Retorna (portal, used_compat_fallback).
    Fallback legado só em host local/plataforma — compatibilidade, não regra SaaS.
    """
    host = request.get_host()
    portal = resolve_portal_from_host(host)
    if portal is not None:
        return portal, False

    if is_local_or_platform_host(host) and getattr(settings, 'TENANT_COMPAT_FALLBACK', False):
        return Portal.get_default(), True
    return None, False
