"""Envio de e-mail da plataforma. Segredos nunca entram em logs ou EmailLog."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.timezone import now

logger = logging.getLogger('plataforma.email')

SUCCESS = 'SUCCESS'
FAILED = 'FAILED'
NOT_CONFIGURED = 'NOT_CONFIGURED'


def mascarar_email(email):
    email = (email or '').strip()
    if '@' not in email:
        return '***'
    local, domain = email.split('@', 1)
    visivel = local[:2] if len(local) > 2 else local[:1]
    return f'{visivel}***@{domain}'


def _sanitizar_erro(texto):
    texto = str(texto or '')[:1500]
    segredos = [
        getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '',
        getattr(settings, 'KIWIFY_WEBHOOK_SECRET', '') or '',
        getattr(settings, 'SECRET_KEY', '') or '',
        getattr(settings, 'DATABASE_URL', '') or '',
    ]
    for segredo in segredos:
        if segredo and len(segredo) > 3:
            texto = texto.replace(segredo, '***')
    return texto


def smtp_pronto_para_envio():
    backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
    if 'dummy' in backend:
        return False
    if 'smtp' in backend.lower() and not (getattr(settings, 'EMAIL_HOST', '') or ''):
        return False
    return True


@dataclass
class EmailResult:
    status: str
    erro: str = ''
    log_id: int | None = None

    @property
    def ok(self):
        return self.status == SUCCESS


def enviar_email(
    destinatario,
    assunto,
    corpo,
    *,
    html=None,
    tipo='notificacao_admin',
    cliente=None,
    usuario=None,
    portal=None,
    remetente=None,
):
    from plataforma.models import EmailLog

    dest = (destinatario or '').strip()
    assunto = (assunto or '')[:200]
    remetente = remetente or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@plataforma.local')
    registro = EmailLog.objects.create(
        cliente=cliente,
        usuario=usuario,
        portal=portal,
        tipo=tipo,
        destinatario=dest or 'invalid@invalid.local',
        assunto=assunto,
        status=EmailLog.STATUS_PENDENTE,
        tentativas=1,
    )
    if not dest or '@' not in dest:
        registro.status = EmailLog.STATUS_FALHOU
        registro.erro = 'Destinatário inválido.'
        registro.save(update_fields=['status', 'erro', 'atualizado_em'])
        return EmailResult(FAILED, registro.erro, registro.pk)

    if not smtp_pronto_para_envio():
        registro.status = EmailLog.STATUS_NAO_CONFIGURADO
        registro.erro = 'Backend de e-mail não envia mensagens.'
        registro.save(update_fields=['status', 'erro', 'atualizado_em'])
        logger.warning('E-mail não enviado (não configurado) para %s', mascarar_email(dest))
        return EmailResult(NOT_CONFIGURED, registro.erro, registro.pk)

    try:
        msg = EmailMultiAlternatives(assunto, corpo, remetente, [dest])
        if html:
            msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
        registro.status = EmailLog.STATUS_ENVIADO
        registro.enviado_em = now()
        registro.erro = ''
        registro.save(update_fields=['status', 'enviado_em', 'erro', 'atualizado_em'])
        logger.info('E-mail %s enviado para %s', tipo, mascarar_email(dest))
        return EmailResult(SUCCESS, '', registro.pk)
    except Exception as exc:
        registro.status = EmailLog.STATUS_FALHOU
        registro.erro = _sanitizar_erro(exc)
        registro.save(update_fields=['status', 'erro', 'atualizado_em'])
        logger.exception('Falha SMTP ao enviar %s para %s', tipo, mascarar_email(dest))
        return EmailResult(FAILED, registro.erro, registro.pk)


def diagnosticar_smtp(conectar=False):
    """Verifica configuração. Só conecta se conectar=True (ação explícita)."""
    backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
    host = getattr(settings, 'EMAIL_HOST', '') or ''
    user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    if 'console' in backend or 'locmem' in backend:
        return {
            'nivel': 'atencao',
            'titulo': 'SMTP de desenvolvimento',
            'detalhe': 'O backend atual não usa Gmail/SMTP de produção.',
        }
    if 'dummy' in backend:
        return {
            'nivel': 'falha',
            'titulo': 'E-mail desativado',
            'detalhe': 'EMAIL_BACKEND dummy não envia mensagens.',
        }
    if not host:
        return {
            'nivel': 'falha',
            'titulo': 'SMTP não configurado',
            'detalhe': 'EMAIL_HOST está vazio.',
        }
    if not conectar:
        return {
            'nivel': 'ok',
            'titulo': 'SMTP configurado',
            'detalhe': f'Host {host} definido. Envie um e-mail de teste para validar o login.',
        }
    try:
        porta = int(getattr(settings, 'EMAIL_PORT', 587) or 587)
        servidor = smtplib.SMTP(host, porta, timeout=8)
        servidor.ehlo()
        if getattr(settings, 'EMAIL_USE_TLS', True):
            servidor.starttls()
            servidor.ehlo()
        senha = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
        if user:
            servidor.login(user, senha)
        servidor.quit()
        return {
            'nivel': 'ok',
            'titulo': 'SMTP funcionando',
            'detalhe': f'Conexão com {host} aceita.',
        }
    except Exception as exc:
        return {
            'nivel': 'falha',
            'titulo': 'Falha no envio',
            'detalhe': _sanitizar_erro(exc),
        }
