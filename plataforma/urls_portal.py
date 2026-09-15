"""URLs canônicas do tenant a partir de slug / host_previsto / custom_domain."""
from plataforma.resolvers import _host_only


def _host_de_custom_domain(valor):
    valor = (valor or '').strip()
    if '://' in valor:
        valor = valor.split('://', 1)[1]
    valor = valor.split('/')[0]
    return _host_only(valor)


def host_publico_portal(portal):
    """Host do site do cliente. custom_domain tem prioridade sobre host_previsto."""
    if portal is None:
        return ''
    custom = _host_de_custom_domain(getattr(portal, 'custom_domain', '') or '')
    if custom:
        return custom
    return (portal.host_previsto or '').strip().lower()


def url_publica_portal(portal, scheme='https'):
    host = host_publico_portal(portal)
    if not host:
        return ''
    return f'{scheme}://{host}/'


def url_app_portal(portal, scheme='https'):
    host = host_publico_portal(portal)
    if not host:
        return ''
    return f'{scheme}://{host}/app/'
