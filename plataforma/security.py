import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger('plataforma.audit')


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded and getattr(settings, 'PRODUCTION', False):
        return forwarded.split(',')[0].strip()[:45]
    return request.META.get('REMOTE_ADDR')


def throttle_blocked(request, scope, limit, window):
    ip = client_ip(request) or 'unknown'
    key = f'throttle:{scope}:{ip}'
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, window)
    return False


def throttle_response():
    return HttpResponse(
        'Muitas tentativas. Aguarde alguns minutos e tente de novo.',
        status=429,
        content_type='text/plain; charset=utf-8',
    )


def safe_redirect(request, target, fallback):
    host = request.get_host()
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={host},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect(fallback)


def log_audit(request, acao, objeto='', objeto_id='', detalhes=None, portal=None):
    from plataforma.models import AuditLog

    user = getattr(request, 'user', None) if request is not None else None
    payload = detalhes or {}
    for secret in ('password', 'senha', 'token', 'secret', 'csrfmiddlewaretoken'):
        payload.pop(secret, None)
    try:
        AuditLog.objects.create(
            portal=portal if portal is not None else getattr(request, 'portal', None),
            usuario=user if user is not None and getattr(user, 'is_authenticated', False) else None,
            acao=acao,
            objeto=objeto[:120],
            objeto_id=str(objeto_id or '')[:40],
            ip=client_ip(request),
            detalhes=payload,
        )
    except Exception:
        logger.exception('Falha ao gravar auditoria (%s)', acao)
