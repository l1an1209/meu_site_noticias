from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .context import bind_request_tenant, clear_tenant_context, set_current_portal
from .models import Membership
from .resolvers import resolve_portal_for_request, resolve_portal_from_host
from .services.pos_login import portal_para_app_em_host_plataforma


def _path_de_app(path):
    path = path or ''
    return path.startswith('/app/') or path == '/app' or path.startswith('/painel/')


class TenantMiddleware:
    """Define request.portal a partir do Host e o contexto usado pelos managers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        bind_request_tenant()
        request.portal = None
        request.portal_from_compat_fallback = False
        request.membership = None
        request.is_platform_master = False
        try:
            portal, used_fallback = resolve_portal_for_request(request)
            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False):
                request.is_platform_master = bool(user.is_superuser)

            # /app/ em host de plataforma: não usar o portal legado do fallback.
            if (
                _path_de_app(request.path)
                and resolve_portal_from_host(request.get_host()) is None
                and not request.is_platform_master
            ):
                portal = portal_para_app_em_host_plataforma(request)
                used_fallback = False

            request.portal = portal
            request.portal_from_compat_fallback = used_fallback
            set_current_portal(portal)

            if user is not None and getattr(user, 'is_authenticated', False):
                if portal is not None:
                    request.membership = (
                        Membership.objects.filter(
                            usuario=user,
                            portal=portal,
                            ativo=True,
                        ).first()
                    )

            if (
                portal is not None
                and portal.status != portal.STATUS_ATIVO
                and not request.is_platform_master
            ):
                path = request.path or ''
                if path.startswith('/webhooks/') or path.startswith('/comece'):
                    return self.get_response(request)
                if path.startswith('/app/') or path.startswith('/painel/') or path.startswith('/master/'):
                    return render(request, 'errors/403.html', status=403)
                return render(request, 'errors/portal_indisponivel.html', status=403)

            return self.get_response(request)
        finally:
            clear_tenant_context()


class SecurityHeadersMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'same-origin')
        response.setdefault('Permissions-Policy', 'geolocation=(self), camera=(), microphone=()')
        response.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
        if 'text/html' in (response.get('Content-Type') or ''):
            response.setdefault(
                'Content-Security-Policy',
                "frame-ancestors 'self'",
            )
        return response
