"""Processamento de webhooks Kiwify, reutilizável pelo endpoint e pelo Master."""
import logging

from django.utils.timezone import now

from plataforma.models import WebhookEvent
from plataforma.services.kiwify import classificar_evento
from plataforma.services.onboarding import (
    cancelar_ou_bloquear,
    marcar_atrasada,
    marcar_pendente,
    provisionar_pagamento_aprovado,
)

logger = logging.getLogger('plataforma.kiwify')


def processar_evento(event, payload=None, request=None, forcar=False):
    """Executa o efeito de um WebhookEvent. Respeita idempotência."""
    payload = payload if payload is not None else (event.payload or {})
    if event.processado and event.status == WebhookEvent.STATUS_PROCESSADO and not forcar:
        return {
            'ok': True,
            'duplicado': True,
            'mensagem': 'Este evento já foi processado.',
        }

    event.tentativas = (event.tentativas or 0) + 1
    event.payload = payload
    tipo = event.tipo
    classe = classificar_evento(tipo)
    try:
        if classe == 'aprovado':
            provisionar_pagamento_aprovado(payload, request=request)
        elif classe == 'pendente':
            marcar_pendente(payload, request=request)
        elif classe == 'atrasada':
            marcar_atrasada(payload, request=request)
        elif classe == 'cancelada':
            cancelar_ou_bloquear(payload, request=request, bloquear=True)
        else:
            event.status = WebhookEvent.STATUS_IGNORADO
            event.processado = True
            event.processado_em = now()
            event.erro = ''
            event.save(update_fields=[
                'status', 'processado', 'processado_em', 'payload', 'erro', 'tentativas',
            ])
            return {'ok': True, 'ignorado': True, 'tipo': tipo, 'classe': classe}

        event.status = WebhookEvent.STATUS_PROCESSADO
        event.processado = True
        event.processado_em = now()
        event.erro = ''
        event.save(update_fields=[
            'status', 'processado', 'processado_em', 'payload', 'erro', 'tentativas',
        ])
        return {'ok': True, 'tipo': tipo, 'classe': classe, 'duplicado': False}
    except ValueError as exc:
        event.status = WebhookEvent.STATUS_ERRO
        event.processado = False
        event.erro = str(exc)[:2000]
        event.save(update_fields=['status', 'processado', 'erro', 'payload', 'tentativas'])
        return {'ok': False, 'erro': str(exc), 'http': 400}
    except Exception as exc:
        logger.exception('Falha no webhook Kiwify')
        event.status = WebhookEvent.STATUS_ERRO
        event.processado = False
        event.erro = str(exc)[:2000]
        event.save(update_fields=['status', 'processado', 'erro', 'payload', 'tentativas'])
        return {'ok': False, 'erro': 'falha ao processar', 'http': 500}


def payload_publico(payload):
    if not isinstance(payload, dict):
        return {}
    ocultar = {'signature', 'token', 'secret', 'password', 'senha', 'authorization'}
    limpo = {}
    for chave, valor in payload.items():
        if str(chave).lower() in ocultar:
            limpo[chave] = '***'
        elif isinstance(valor, dict):
            limpo[chave] = payload_publico(valor)
        else:
            limpo[chave] = valor
    return limpo
