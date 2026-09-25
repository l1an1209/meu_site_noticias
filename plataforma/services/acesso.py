"""Link seguro de acesso (redefinição de senha). Não envia senha permanente."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from plataforma.models import EmailLog
from plataforma.services.email import EmailResult, FAILED, enviar_email
from plataforma.urls_portal import host_publico_portal, url_app_portal, url_publica_portal

User = get_user_model()


def _base_url(request=None, portal=None):
    site = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if site:
        return site
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    if portal is not None:
        host = host_publico_portal(portal)
        if host:
            return f'https://{host}'.rstrip('/')
    return 'https://localhost'


def _url_plataforma(request=None):
    """Entrada da plataforma (apex), não o host do tenant."""
    site = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if site:
        return site
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    base = getattr(settings, 'TENANT_BASE_DOMAIN', 'portalnoticias.com.br')
    return f'https://{base}'.rstrip('/')


def _portal_em_onboarding(portal):
    return portal is not None and not portal.setup_concluido


def link_redefinicao(usuario, request=None, portal=None):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    path = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
    if _portal_em_onboarding(portal):
        base = _url_plataforma(request)
    else:
        base = _base_url(request, portal)
    return f'{base}{path}'


def _url_entrar_plataforma(request=None):
    return f"{_url_plataforma(request)}{reverse('entrar')}"


def enviar_acesso(usuario, portal, request=None, tipo=EmailLog.TIPO_ONBOARDING, cliente=None):
    if not usuario or not usuario.email:
        return EmailResult(FAILED, 'Usuário sem e-mail.')
    link = link_redefinicao(usuario, request=request, portal=portal)
    if _portal_em_onboarding(portal):
        entrar = _url_entrar_plataforma(request)
        assunto = 'Seu acesso à plataforma foi criado'
        corpo = (
            f'Olá, {usuario.get_short_name() or usuario.username}.\n\n'
            f'Pagamento confirmado!\n\n'
            f'Seu acesso à plataforma foi criado.\n\n'
            f'Antes de acessar o painel, você precisa concluir a configuração '
            f'inicial do seu portal.\n\n'
            f'Durante essa configuração você poderá definir:\n'
            f'- o nome do seu portal;\n'
            f'- o endereço/subdomínio que deseja utilizar.\n\n'
            f'Depois da configuração, você terá o endereço definitivo do portal.\n\n'
            f'Acesse a plataforma:\n'
            f'{entrar}\n\n'
            f'Depois do login, você será direcionado automaticamente para a '
            f'configuração inicial.\n\n'
            f'Usuário: {usuario.username}\n\n'
            f'Defina sua senha neste link (válido por cerca de uma hora):\n'
            f'{link}\n\n'
            f'Não compartilhe este link. Se você não esperava este e-mail, ignore-o.\n'
        )
    else:
        nome_portal = portal.nome if portal else 'seu portal'
        site = url_publica_portal(portal) if portal else ''
        painel = url_app_portal(portal) if portal else ''
        assunto = f'Acesso ao {nome_portal}'
        corpo = (
            f'Olá, {usuario.get_short_name() or usuario.username}.\n\n'
            f'Seu portal foi criado com sucesso.\n\n'
            f'Acessar meu site\n'
            f'{site}\n\n'
            f'Administrar meu portal\n'
            f'{painel}\n\n'
            f'Usuário: {usuario.username}\n\n'
            f'Defina sua senha neste link (válido por cerca de uma hora):\n'
            f'{link}\n\n'
            f'Não compartilhe este link. Se você não esperava este e-mail, ignore-o.\n'
        )
    return enviar_email(
        usuario.email,
        assunto,
        corpo,
        tipo=tipo,
        cliente=cliente,
        usuario=usuario,
        portal=portal,
    )


def enviar_boas_vindas_gratuito(usuario, portal, request=None, cliente=None):
    """E-mail do cadastro gratuito. Não envia senha e não altera o fluxo da Kiwify."""
    if not usuario or not usuario.email:
        return EmailResult(FAILED, 'Usuário sem e-mail.')
    nome = usuario.get_short_name() or usuario.username
    portal_nome = (portal.nome if portal else '') or 'seu portal'
    entrar = _url_entrar_plataforma(request)
    assunto = 'Seu portal foi criado no PortalUP'
    corpo = (
        f'Olá, {nome}.\n\n'
        f'Seu cadastro no PortalUP foi concluído.\n\n'
        f'O portal {portal_nome} foi criado.\n\n'
        f'Você já pode acessar o PortalUP e seguir o passo a passo '
        f'para configurar o portal.\n\n'
        f'Acessar o PortalUP:\n'
        f'{entrar}\n\n'
        f'Se você não fez este cadastro, ignore este e-mail.\n'
    )
    return enviar_email(
        usuario.email,
        assunto,
        corpo,
        tipo=EmailLog.TIPO_ONBOARDING,
        cliente=cliente,
        usuario=usuario,
        portal=portal,
    )


def usuario_do_cliente(cliente):
    if cliente is None or not cliente.email:
        return None
    return User.objects.filter(email__iexact=cliente.email).order_by('id').first()
