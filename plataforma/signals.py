from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from plataforma.security import log_audit


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    log_audit(request, 'login', objeto='User', objeto_id=user.pk)


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    log_audit(request, 'logout', objeto='User', objeto_id=getattr(user, 'pk', ''))


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request, **kwargs):
    username = (credentials or {}).get('username', '')[:80]
    log_audit(request, 'login_falhou', objeto='User', detalhes={'username': username})
