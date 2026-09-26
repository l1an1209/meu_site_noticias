"""Leitura dos eventos e sessões já gravados pelo Analytics.

Não calcula métrica nova e não grava registro. O recorte de período e de
portal é o mesmo de `periodo_de_params`, `portal_filtrado` e `_qs_eventos`.
"""
from django.db.models import Q

from plataforma.models import AnalyticsSession
from plataforma.services.analytics import _qs_eventos, periodo_de_params, portal_filtrado


def ler(params):
    periodo, inicio, fim = periodo_de_params(params)
    portal = portal_filtrado(params)
    return {
        'periodo': periodo,
        'inicio': inicio,
        'fim': fim,
        'portal': portal,
        'eventos': _qs_eventos(inicio, fim, portal),
        'sessoes': _sessoes(inicio, fim, portal),
    }


def _sessoes(inicio, fim, portal):
    """Mesmo recorte de sessão usado no dashboard, sem alterar o cálculo dele."""
    qs = AnalyticsSession.objects.filter(criado_em__gte=inicio, criado_em__lte=fim)
    if portal is None:
        return qs
    return qs.filter(Q(portal=portal) | Q(eventos__portal=portal)).distinct()
