"""Métricas do Adaptive Engine, calculadas sobre a leitura da sub-fase 1.1.

Não grava evento, não altera o dashboard e não coloca a compra numa fila
linear. Taxa sem denominador volta sem amostra. Amostra abaixo do mínimo
continua numérica, marcada como baixa confiança.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils.timezone import localtime

from plataforma.models import AnalyticsSession
from plataforma.services.adaptive_engine.leitura import ler
from plataforma.services.analytics import _ids

AMOSTRA_MINIMA = 30
TIPOS_PAGEVIEW = (
    'page_view', 'view_home', 'view_plans', 'initiate_checkout', 'registration_start',
)


def calcular(params):
    recorte = ler(params)
    bloco = _bloco(recorte)
    bloco['comparacao'] = _bloco(ler(_params_anterior(recorte, params)))
    return bloco


def _params_anterior(recorte, params):
    inicio = localtime(recorte['inicio']).date()
    fim = localtime(recorte['fim']).date()
    dias = (fim - inicio).days + 1
    ate = inicio - timedelta(days=1)
    de = ate - timedelta(days=dias - 1)
    novo = {'periodo': 'custom', 'de': de.isoformat(), 'ate': ate.isoformat()}
    if params.get('portal'):
        novo['portal'] = params.get('portal')
    return novo


def _bloco(recorte):
    eventos = recorte['eventos']
    lista_sessoes = list(recorte['sessoes'])
    base = len(lista_sessoes) or eventos.values('sessao_id').distinct().count()

    cliques_gratis = _ids(eventos.filter(tipo='click_subscribe', path__startswith='/app/comecar'))
    portais = _ids(eventos.filter(tipo='portal_created'))
    cliques_pagos = _ids(eventos.filter(tipo='click_plan'))
    checkouts = _ids(eventos.filter(tipo='initiate_checkout'))
    planos = _ids(eventos.filter(tipo='view_plans'))
    compras = _ids(eventos.filter(tipo='purchase'))
    com_jornada = _ids(eventos.exclude(tipo='purchase'))
    portal_no_fluxo = portais & cliques_gratis
    checkout_no_fluxo = checkouts & cliques_pagos
    entrada_direta = checkouts - cliques_pagos
    orfas = compras - com_jornada

    return {
        'periodo': recorte['periodo'],
        'portal_id': recorte['portal'].pk if recorte['portal'] else None,
        'aquisicao': {
            'sessoes': _contagem(len(lista_sessoes), base),
            'visitantes': _contagem(eventos.values('sessao_id').distinct().count(), base),
            'pageviews': _contagem(eventos.filter(tipo__in=TIPOS_PAGEVIEW).count(), base),
            'origem': _distribuicao([s.origem_label() for s in lista_sessoes], len(lista_sessoes)),
            'dispositivo': _distribuicao(
                [s.get_dispositivo_display() for s in lista_sessoes], len(lista_sessoes),
            ),
            'utm_campaign': _distribuicao(
                [s.utm_campaign for s in lista_sessoes if s.utm_campaign],
                sum(1 for s in lista_sessoes if s.utm_campaign),
            ),
        },
        'funil_gratis': {
            'cliques': _contagem(len(cliques_gratis), base),
            'portal_criado': _contagem(len(portais), base),
            'portal_no_fluxo': _contagem(len(portal_no_fluxo), base),
            'sem_clique': _contagem(len(portais - cliques_gratis), base),
        },
        'funil_pago': {
            'cliques': _contagem(len(cliques_pagos), base),
            'checkout_no_fluxo': _contagem(len(checkout_no_fluxo), base),
        },
        'funil_comparacao': {
            'view_plans': _contagem(len(planos), base),
        },
        'checkout_direto': {
            'sessoes': _contagem(len(entrada_direta), base),
            'proporcao': _taxa(len(entrada_direta), len(checkouts)),
        },
        'compras': {
            'sessoes': _contagem(len(compras), base),
            'receita': _receita(eventos),
            'orfas': _contagem(len(orfas), len(compras)),
        },
        'conversoes': {
            'gratis_clique_para_portal': _taxa(len(portal_no_fluxo), len(cliques_gratis)),
            'pago_clique_para_checkout': _taxa(len(checkout_no_fluxo), len(cliques_pagos)),
            'pago_por_dispositivo': _taxas_por(cliques_pagos, checkout_no_fluxo, _dispositivo),
            'pago_por_origem': _taxas_por(cliques_pagos, checkout_no_fluxo, _origem),
            'pago_por_plano': _taxas_plano(eventos, checkout_no_fluxo),
        },
    }


def _contagem(valor, base):
    if base <= 0:
        return {'valor': None, 'amostra': 0, 'estado': 'sem_amostra'}
    return {
        'valor': valor,
        'amostra': base,
        'estado': 'ok' if base >= AMOSTRA_MINIMA else 'baixa_confianca',
    }


def _taxa(numerador, denominador):
    if not denominador:
        return {'valor': None, 'amostra': 0, 'estado': 'sem_amostra'}
    return {
        'valor': round(numerador / denominador, 4),
        'amostra': denominador,
        'estado': 'ok' if denominador >= AMOSTRA_MINIMA else 'baixa_confianca',
    }


def _distribuicao(chaves, base):
    if base <= 0:
        return {'itens': [], 'amostra': 0, 'estado': 'sem_amostra'}
    mapa = {}
    for chave in chaves:
        mapa[chave] = mapa.get(chave, 0) + 1
    return {
        'itens': [
            {'chave': chave, 'sessoes': n}
            for chave, n in sorted(mapa.items(), key=lambda item: (-item[1], item[0]))
        ],
        'amostra': base,
        'estado': 'ok' if base >= AMOSTRA_MINIMA else 'baixa_confianca',
    }


def _receita(eventos):
    compras = eventos.filter(tipo='purchase')
    if not compras.exists():
        return {'valor': None, 'amostra': 0, 'estado': 'sem_amostra'}
    total = Decimal('0')
    com_valor = 0
    for extra in compras.values_list('extra', flat=True):
        try:
            valor = Decimal(str((extra or {}).get('valor') or '0'))
        except (InvalidOperation, TypeError):
            continue
        if (extra or {}).get('valor') in (None, ''):
            continue
        total += valor
        com_valor += 1
    if com_valor == 0:
        return {'valor': None, 'amostra': compras.count(), 'estado': 'sem_amostra'}
    return {
        'valor': total,
        'amostra': com_valor,
        'estado': 'ok' if com_valor >= AMOSTRA_MINIMA else 'baixa_confianca',
    }


def _taxas_por(denominador_ids, numerador_ids, grupo):
    if not denominador_ids:
        return {'itens': [], 'estado': 'sem_amostra'}
    sessoes = {
        sessao.id: sessao
        for sessao in AnalyticsSession.objects.filter(pk__in=denominador_ids)
    }
    grupos = {}
    for sid in denominador_ids:
        sessao = sessoes.get(sid)
        chave = grupo(sessao) if sessao else 'Desconhecido'
        grupos.setdefault(chave, set()).add(sid)
    return {
        'itens': [
            {
                'chave': chave,
                'taxa': _taxa(len(ids & numerador_ids), len(ids)),
            }
            for chave, ids in sorted(grupos.items())
        ],
        'estado': 'ok',
    }


def _taxas_plano(eventos, checkout_no_fluxo):
    grupos = {}
    for sessao_id, extra in eventos.filter(tipo='click_plan').values_list('sessao_id', 'extra'):
        plano = str((extra or {}).get('plano') or '').strip()
        if not plano:
            continue
        grupos.setdefault(plano, set()).add(sessao_id)
    if not grupos:
        return {'itens': [], 'estado': 'sem_amostra'}
    return {
        'itens': [
            {'chave': plano, 'taxa': _taxa(len(ids & checkout_no_fluxo), len(ids))}
            for plano, ids in sorted(grupos.items())
        ],
        'estado': 'ok',
    }


def _dispositivo(sessao):
    return sessao.get_dispositivo_display()


def _origem(sessao):
    return sessao.origem_label()
