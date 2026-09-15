import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from plataforma.models import WebhookEvent
from plataforma.services.kiwify import tipo_evento, webhook_autentico
from plataforma.services.webhooks import processar_evento

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

        resultado = processar_evento(event, payload=payload, request=request)
        if resultado.get('duplicado'):
            return JsonResponse({'ok': True, 'duplicado': True})
        if resultado.get('ok'):
            corpo = {'ok': True, 'tipo': tipo, 'novo': created}
            if resultado.get('ignorado'):
                corpo['ignorado'] = True
            else:
                corpo['classe'] = resultado.get('classe')
            return JsonResponse(corpo)
        status = resultado.get('http', 500)
        erro = resultado.get('erro', 'falha ao processar')
        if status == 500:
            return JsonResponse({'ok': False, 'erro': 'falha ao processar'}, status=500)
        return JsonResponse({'ok': False, 'erro': erro}, status=status)
