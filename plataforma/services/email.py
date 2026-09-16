"""Envio de e-mail da plataforma via API HTTPS da Resend. Segredos nunca entram em logs ou EmailLog."""
from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger('plataforma.email')

SUCCESS = 'SUCCESS'
FAILED = 'FAILED'
NOT_CONFIGURED = 'NOT_CONFIGURED'
RESEND_API_URL = 'https://api.resend.com/emails'
RESEND_TIMEOUT = 15


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
        getattr(settings, 'RESEND_API_KEY', '') or '',
    ]
    for segredo in segredos:
        if segredo and len(segredo) > 3:
            texto = texto.replace(segredo, '***')
    texto = texto.replace('Bearer ', 'Bearer ***')
    return texto


def _resend_api_key():
    return (getattr(settings, 'RESEND_API_KEY', '') or '').strip()


def smtp_pronto_para_envio():
    """Pronto = chave da Resend presente. Nome mantido pelos chamadores."""
    return bool(_resend_api_key())


def _mensagem_erro_http(status, corpo):
    detalhe = ''
    try:
        dados = json.loads(corpo or '')
        detalhe = str(dados.get('message') or dados.get('error') or '')[:400]
    except (TypeError, ValueError):
        detalhe = (corpo or '')[:400]
    texto = f'Resend HTTP {status}'
    if detalhe:
        texto = f'{texto}: {detalhe}'
    return _sanitizar_erro(texto)


def _post_resend(payload):
    """POST HTTPS para api.resend.com. Isolado para testes."""
    chave = _resend_api_key()
    if not chave:
        raise RuntimeError('RESEND_API_KEY ausente.')
    corpo = json.dumps(payload).encode('utf-8')
    pedido = Request(
        RESEND_API_URL,
        data=corpo,
        method='POST',
        headers={
            'Authorization': f'Bearer {chave}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
    )
    try:
        with urlopen(pedido, timeout=RESEND_TIMEOUT, context=ssl.create_default_context()) as resp:
            bruto = resp.read().decode('utf-8', errors='replace')
            status = getattr(resp, 'status', 200)
            if status >= 400:
                raise RuntimeError(_mensagem_erro_http(status, bruto))
            return json.loads(bruto) if bruto else {}
    except HTTPError as exc:
        bruto = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(_mensagem_erro_http(exc.code, bruto)) from None
    except URLError as exc:
        raise RuntimeError(_sanitizar_erro(f'Falha HTTPS Resend: {exc.reason}')) from None


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

    payload = {
        'from': remetente,
        'to': [dest],
        'subject': assunto,
        'text': corpo or '',
    }
    if html:
        payload['html'] = html

    try:
        _post_resend(payload)
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
        logger.error(
            'Falha ao enviar %s para %s: %s',
            tipo,
            mascarar_email(dest),
            _sanitizar_erro(exc),
        )
        return EmailResult(FAILED, registro.erro, registro.pk)


def diagnosticar_smtp(conectar=False):
    """Diagnóstico da API Resend. Nome mantido pelos chamadores do Master/saúde."""
    chave = _resend_api_key()
    if not chave:
        return {
            'nivel': 'falha',
            'titulo': 'E-mail não configurado',
            'detalhe': 'RESEND_API_KEY está vazia.',
        }
    if not conectar:
        return {
            'nivel': 'ok',
            'titulo': 'Resend configurado',
            'detalhe': 'API HTTPS da Resend com chave definida. Envie um e-mail de teste para validar.',
        }
    pedido = Request(
        RESEND_API_URL,
        method='GET',
        headers={
            'Authorization': f'Bearer {chave}',
            'Accept': 'application/json',
        },
    )
    try:
        with urlopen(pedido, timeout=8, context=ssl.create_default_context()) as resp:
            status = getattr(resp, 'status', 0)
            resp.read()
        return {
            'nivel': 'ok',
            'titulo': 'Resend alcançável',
            'detalhe': f'HTTPS api.resend.com respondeu ({status}).',
        }
    except HTTPError as exc:
        # 401/404/405 ainda provam TLS/TCP até a API, sem enviar e-mail.
        if exc.code in {401, 403, 404, 405, 422}:
            return {
                'nivel': 'ok',
                'titulo': 'Resend alcançável',
                'detalhe': 'HTTPS api.resend.com respondeu.',
            }
        return {
            'nivel': 'falha',
            'titulo': 'Falha no envio',
            'detalhe': _mensagem_erro_http(exc.code, exc.read().decode('utf-8', errors='replace')),
        }
    except Exception as exc:
        return {
            'nivel': 'falha',
            'titulo': 'Falha no envio',
            'detalhe': _sanitizar_erro(exc),
        }
