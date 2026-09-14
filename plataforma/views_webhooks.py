import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from plataforma.models import WebhookEvent
from plataforma.services.kiwify import (
    classificar_evento,
    tipo_evento,
    webhook_autentico,
)
from plataforma.services.onboarding import (
    cancelar_ou_bloquear,
    marcar_atrasada,
    marcar_pendente,
    provisionar_pagamento_aprovado,
)

logger = logging.getLogger('plataforma.kiwify')


def _payload(request):
    if request.content_type and 'application/json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return None
    return request.POST.dict()


@csrf_exempt
@require_POST
def kiwify_webhook(request):
    payload = _payload(request)
    if payload is None:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido'}, status=400)

    if not webhook_autentico(payload):
        return JsonResponse({'ok': False, 'erro': 'assinatura inválida'}, status=401)

    tipo = tipo_evento(payload)
    order_id = str(payload.get('order_id') or '')
    if not order_id:
        return JsonResponse({'ok': False, 'erro': 'order_id ausente'}, status=400)

    with transaction.atomic():
        event, created = WebhookEvent.objects.select_for_update().get_or_create(
            provedor='kiwify',
            tipo=tipo,
            id_externo=order_id,
            defaults={'payload': payload, 'status': WebhookEvent.STATUS_RECEBIDO},
        )
        if event.processado:
            return JsonResponse({'ok': True, 'duplicado': True})

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
                event.payload = payload
                event.save(update_fields=['status', 'processado', 'processado_em', 'payload'])
                return JsonResponse({'ok': True, 'ignorado': True, 'tipo': tipo})

            event.status = WebhookEvent.STATUS_PROCESSADO
            event.processado = True
            event.processado_em = now()
            event.payload = payload
            event.erro = ''
            event.save(update_fields=['status', 'processado', 'processado_em', 'payload', 'erro'])
            return JsonResponse({'ok': True, 'tipo': tipo, 'classe': classe, 'novo': created})
        except ValueError as exc:
            event.status = WebhookEvent.STATUS_ERRO
            event.erro = str(exc)[:2000]
            event.payload = payload
            event.save(update_fields=['status', 'erro', 'payload'])
            return JsonResponse({'ok': False, 'erro': str(exc)}, status=400)
        except Exception as exc:
            logger.exception('Falha no webhook Kiwify')
            event.status = WebhookEvent.STATUS_ERRO
            event.erro = str(exc)[:2000]
            event.payload = payload
            event.save(update_fields=['status', 'erro', 'payload'])
            return JsonResponse({'ok': False, 'erro': 'falha ao processar'}, status=500)
