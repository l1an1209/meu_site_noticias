"""Destino após login/cadastro. Não substitui Host → Portal → Membership."""
from urllib.parse import urlparse

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from plataforma.models import Portal
from plataforma.permissions import is_platform_master, membership_for
from plataforma.resolvers import resolve_portal_from_host


def _host_only(host):
    return (host or '').split(':')[0].lower().strip()


def _port_suffix(request):
    host = request.get_host() or ''
    if host.count(':') == 1 and not host.endswith(']'):
        return ':' + host.rsplit(':', 1)[1]
    return ''


def portais_administraveis(user):
    """Portais que o usuário pode administrar: Membership ativo + portal ativo."""
    if not user or not user.is_authenticated:
        return Portal.objects.none()
    return (
        Portal.objects.filter(
            status=Portal.STATUS_ATIVO,
            membros__usuario=user,
            membros__ativo=True,
        )
        .distinct()
        .order_by('nome', 'id')
    )


def portais_indisponiveis(user):
    if not user or not user.is_authenticated:
        return Portal.objects.none()
    return (
        Portal.objects.filter(
            membros__usuario=user,
            membros__ativo=True,
        )
        .exclude(status=Portal.STATUS_ATIVO)
        .distinct()
        .order_by('nome', 'id')
    )


def tenant_host_for_portal(request, portal):
    """Host que o middleware resolve para este portal. Não escolhe outro tenant."""
    if portal.custom_domain:
        return _host_only(portal.custom_domain)

    current_host = request.get_host()
    current_portal = resolve_portal_from_host(current_host)
    host_only = _host_only(current_host)
    if current_portal is not None and '.' in host_only:
        parent = host_only.split('.', 1)[1]
        return f'{portal.slug}.{parent}'
    return portal.host_previsto


SESSION_PORTAL_KEY = 'app_portal_id'


def eh_host_dev_local(request):
    return _host_only(request.get_host()) in {'localhost', '127.0.0.1', 'testserver'}


def gravar_portal_sessao(request, portal):
    if portal is not None:
        request.session[SESSION_PORTAL_KEY] = portal.pk


def portal_da_sessao(request, user):
    pk = request.session.get(SESSION_PORTAL_KEY)
    if not pk:
        return None
    return portais_administraveis(user).filter(pk=pk).first()


def portal_para_app_em_host_plataforma(request):
    """
    Em localhost/127.0.0.1 o Host não identifica tenant.
    Usa a sessão (escolha do usuário) ou o único Membership ativo.
    Não usa Portal.get_default() e não pega o primeiro de vários.
    """
    user = getattr(request, 'user', None)
    escolhido = portal_da_sessao(request, user)
    if escolhido is not None:
        return escolhido
    administraveis = list(portais_administraveis(user))
    if len(administraveis) == 1:
        gravar_portal_sessao(request, administraveis[0])
        return administraveis[0]
    return None


def app_url_for_portal(request, portal):
    """
    URL de /app/ no Host que o middleware associa a este portal.
    Em 127.0.0.1/localhost grava a sessão e usa /app/ relativo (sem domínio inventado).
    """
    gravar_portal_sessao(request, portal)
    current_host = request.get_host()
    current = resolve_portal_from_host(current_host)
    if current is not None and current.pk == portal.pk:
        return reverse('app_home')
    if eh_host_dev_local(request):
        return reverse('app_home')

    scheme = 'https' if request.is_secure() else 'http'
    host = tenant_host_for_portal(request, portal)
    return f'{scheme}://{host}{_port_suffix(request)}{reverse("app_home")}'


def _next_seguro(request):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if not target:
        return ''
    if url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return ''


def _path_of(target):
    parsed = urlparse(target)
    path = parsed.path or target
    if not path.startswith('/'):
        path = '/' + path
    return path


def next_autorizado(request, user, target):
    """next não autoriza Master/App. Só segue se o usuário já teria acesso naquele path."""
    path = _path_of(target)
    if path.startswith('/master'):
        return is_platform_master(user)
    if path.startswith('/app/') or path == '/app' or path.startswith('/painel'):
        if is_platform_master(user):
            return True
        portal = getattr(request, 'portal', None)
        if portal is None or portal.status != Portal.STATUS_ATIVO:
            return False
        return membership_for(user, portal) is not None
    return True


def destino_pos_login(request, user):
    nxt = _next_seguro(request)
    if nxt and next_autorizado(request, user, nxt):
        return nxt

    if is_platform_master(user):
        return reverse('master_home')

    administraveis = list(portais_administraveis(user))
    if len(administraveis) == 1:
        return app_url_for_portal(request, administraveis[0])
    if len(administraveis) > 1:
        return reverse('selecionar_portal')

    if portais_indisponiveis(user).exists():
        return reverse('acesso_portal_indisponivel')

    return reverse('pagina_vendas')
