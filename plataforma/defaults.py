from django.conf import settings

from .context import get_current_portal, is_request_bound


def assign_portal(instance):
    """Define portal pelo contexto da requisição. Fallback legado só fora de HTTP."""
    if getattr(instance, 'portal_id', None):
        return

    portal = get_current_portal()
    if portal is not None:
        instance.portal = portal
        return

    if is_request_bound():
        raise ValueError(
            'Não há portal no contexto desta requisição. '
            'O tenant vem do Host (subdomínio) ou da autorização — '
            'não use um portal padrão em produção.'
        )

    if getattr(settings, 'TENANT_COMPAT_FALLBACK', False):
        from .models import Portal
        legado = Portal.get_default()
        if legado is not None:
            instance.portal = legado
            return

    raise ValueError(
        'Portal obrigatório. Informe portal=... ou resolva o tenant pelo Host.'
    )


def assign_default_portal(instance):
    """Alias de compatibilidade (etapa 1). Não é a regra definitiva do SaaS."""
    assign_portal(instance)
