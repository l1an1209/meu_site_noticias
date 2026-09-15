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


def link_redefinicao(usuario, request=None, portal=None):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    path = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
    return f'{_base_url(request, portal)}{path}'


def enviar_acesso(usuario, portal, request=None, tipo=EmailLog.TIPO_ONBOARDING, cliente=None):
    if not usuario or not usuario.email:
        return EmailResult(FAILED, 'Usuário sem e-mail.')
    link = link_redefinicao(usuario, request=request, portal=portal)
    nome_portal = portal.nome if portal else 'seu portal'
    site = url_publica_portal(portal) if portal else ''
    painel = url_app_portal(portal) if portal else ''
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
        f'Acesso ao {nome_portal}',
        corpo,
        tipo=tipo,
        cliente=cliente,
        usuario=usuario,
        portal=portal,
    )


def usuario_do_cliente(cliente):
    if cliente is None or not cliente.email:
        return None
    return User.objects.filter(email__iexact=cliente.email).order_by('id').first()
