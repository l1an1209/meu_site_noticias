"""Integração com webhooks de checkout da Kiwify (produto / assinatura).

Eventos oficiais do painel (docs.kiwify.com.br, trigger enum):
- compra_aprovada, compra_recusada, compra_reembolsada, chargeback
- pix_gerado, boleto_gerado, carrinho_abandonado
- subscription_canceled, subscription_late, subscription_renewed

O JSON de entrega usa também `webhook_event_type` em inglês
(ex.: order_approved) e o objeto `Subscription` com id, status,
start_date, next_payment e plan.id — campos documentados em exemplos
oficiais de payload, não inventados.

Autenticidade (checkout do painel, não a API bancária):

A API bancária (docs.kiwify.com.br/api-reference/banking/webhook-headers)
usa Ed25519 em headers (`x-kiwify-digital-signature`). Isso NÃO é o
webhook de produto/assinatura do painel (triggers compra_aprovada,
token, axios POST com `?signature=`).

O webhook do painel (public-api `/webhooks`, campo `token`) envia a
assinatura na query string. O digest tem 40 hex = SHA-1, não MD5 (32).

Fórmula aceita (todas exigem o token; nenhuma aceita assinatura vazia):
- HMAC-SHA1(chave=token, mensagem=order_id) — hex
- SHA1(order_id + token) — hex, variante documentada em exemplos PHP
- HMAC-SHA1(chave=token, mensagem=corpo JSON bruto) — n8n / axios

Segredo só via KIWIFY_WEBHOOK_SECRET. Não registrar token nem assinatura.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, is_naive


EVENTOS_APROVADOS = {
    'compra_aprovada',
    'order_approved',
    'subscription_renewed',
}
EVENTOS_PENDENTES = {
    'pix_gerado',
    'boleto_gerado',
    'compra_recusada',
    'order_rejected',
}
EVENTOS_ATRASO = {'subscription_late'}
EVENTOS_CANCELAMENTO = {
    'subscription_canceled',
    'compra_reembolsada',
    'order_refunded',
    'chargeback',
}


def _hex_igual(esperado, recebido):
    esperado = (esperado or '').lower()
    recebido = (recebido or '').lower()
    if not esperado or not recebido or len(esperado) != len(recebido):
        return False
    return hmac.compare_digest(esperado, recebido)


def _hmac_sha1_hex(mensagem, secret):
    if isinstance(mensagem, str):
        mensagem = mensagem.encode('utf-8')
    return hmac.new(secret.encode('utf-8'), mensagem, hashlib.sha1).hexdigest()


def assinatura_kiwify(order_id, secret):
    """HMAC-SHA1 do order_id com o token do webhook como chave (hex, 40 chars)."""
    return _hmac_sha1_hex(str(order_id or ''), secret or '')


def webhook_autentico(payload, secret=None, signature=None, corpo_bruto=None):
    secret = (secret if secret is not None else getattr(settings, 'KIWIFY_WEBHOOK_SECRET', '')) or ''
    if not secret:
        return False
    payload = payload or {}
    order_id = str(payload.get('order_id') or '')
    recebido = str(signature or '').strip() or str(payload.get('signature') or '').strip()
    if not recebido:
        return False

    candidatos = []
    if order_id:
        candidatos.append(assinatura_kiwify(order_id, secret))
        candidatos.append(hashlib.sha1(f'{order_id}{secret}'.encode('utf-8')).hexdigest())
    if corpo_bruto:
        bruto = corpo_bruto if isinstance(corpo_bruto, (bytes, bytearray)) else str(corpo_bruto).encode('utf-8')
        if bruto:
            candidatos.append(_hmac_sha1_hex(bytes(bruto), secret))

    return any(_hex_igual(candidato, recebido) for candidato in candidatos)


def tipo_evento(payload):
    tipo = (payload.get('webhook_event_type') or payload.get('event') or '').strip()
    if tipo:
        return tipo
    status = (payload.get('order_status') or '').lower()
    if status == 'paid':
        return 'order_approved'
    if status in {'refunded', 'chargedback'}:
        return 'order_refunded'
    return 'desconhecido'


def _dt(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).replace(' ', 'T', 1)
        dt = parse_datetime(texto)
        if dt is None:
            try:
                dt = datetime.fromisoformat(texto.replace('Z', '+00:00'))
            except ValueError:
                return None
    if is_naive(dt):
        dt = make_aware(dt)
    return dt


def extrair_cliente(payload):
    customer = payload.get('Customer') or {}
    email = (customer.get('email') or '').strip().lower()
    nome = (customer.get('full_name') or customer.get('first_name') or '').strip()
    telefone = str(customer.get('mobile') or '').strip()
    cidade = (customer.get('city') or '').strip()
    estado = (customer.get('state') or '').strip()
    return {
        'email': email,
        'nome': nome or (email.split('@')[0] if email else 'Cliente'),
        'telefone': telefone[:30],
        'cidade': cidade or 'Brasil',
        'estado': estado or 'BR',
    }


def extrair_assinatura_kiwify(payload):
    sub = payload.get('Subscription') or {}
    plan = sub.get('plan') or {}
    product = payload.get('Product') or {}
    return {
        'subscription_id': str(sub.get('id') or ''),
        'order_id': str(payload.get('order_id') or ''),
        'transaction_id': str(
            payload.get('payment_merchant_id') or payload.get('order_ref') or ''
        ),
        'plan_id': str(plan.get('id') or ''),
        'plan_name': str(plan.get('name') or ''),
        'product_id': str(product.get('product_id') or ''),
        'product_name': str(product.get('product_name') or ''),
        'start_date': _dt(sub.get('start_date') or payload.get('approved_date')),
        'next_payment': _dt(sub.get('next_payment')),
    }


def classificar_evento(tipo):
    if tipo in EVENTOS_APROVADOS:
        return 'aprovado'
    if tipo in EVENTOS_PENDENTES:
        return 'pendente'
    if tipo in EVENTOS_ATRASO:
        return 'atrasada'
    if tipo in EVENTOS_CANCELAMENTO:
        return 'cancelada'
    return 'ignorado'
