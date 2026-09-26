"""Persistência de experimentos sugeridos.

Grava, consulta e muda status. Não calcula métrica, não lê Analytics
e não executa teste.

Status reservado para fase futura, ainda não implementado: inconclusivo.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils.timezone import now

from plataforma.models import AdaptiveExperiment, Portal
from plataforma.services.adaptive_engine.experiments import ExperimentSuggestion

_TODOS = object()
_OBSERVACAO_SEM_BASELINE = 'baseline indisponível no momento da criação'
_TRANSICOES = {
    AdaptiveExperiment.STATUS_AGUARDANDO_APROVACAO: {
        AdaptiveExperiment.STATUS_APROVADO,
        AdaptiveExperiment.STATUS_CANCELADO,
    },
    AdaptiveExperiment.STATUS_APROVADO: {
        AdaptiveExperiment.STATUS_EXECUTANDO,
        AdaptiveExperiment.STATUS_CANCELADO,
    },
    AdaptiveExperiment.STATUS_EXECUTANDO: {
        AdaptiveExperiment.STATUS_CONCLUIDO,
        AdaptiveExperiment.STATUS_CANCELADO,
    },
}


def pode_transicionar(status_atual, status_novo):
    """Retorna True se a transição é permitida. Não altera nada."""
    return status_novo in _TRANSICOES.get(status_atual, ())


def criar_experimento(
    sugestao,
    *,
    area,
    portal=None,
    valor_baseline=None,
    amostra_baseline=0,
    periodo_baseline_inicio=None,
    periodo_baseline_fim=None,
):
    """Grava a sugestão. Sem snapshot, a baseline fica vazia e o registro nasce mesmo assim."""
    if not _sugestao_valida(sugestao, area, portal):
        return None
    existente = (
        AdaptiveExperiment.objects
        .filter(insight_id=sugestao.insight_id, status__in=AdaptiveExperiment.STATUS_ATIVOS)
        .order_by('criado_em')
        .first()
    )
    if existente is not None:
        return existente
    valor = _decimal(valor_baseline)
    if valor is None:
        amostra = 0
        observacoes = _OBSERVACAO_SEM_BASELINE
    else:
        amostra = _inteiro(amostra_baseline)
        observacoes = ''
    return AdaptiveExperiment.objects.create(
        portal=portal,
        insight_id=sugestao.insight_id,
        tipo=sugestao.tipo,
        area=area.strip(),
        titulo=sugestao.titulo,
        hipotese=sugestao.hipotese,
        metrica_principal=sugestao.metrica_principal,
        metrica_referencia=sugestao.metrica_referencia,
        valor_baseline=valor,
        amostra_baseline=amostra,
        periodo_baseline_inicio=_data(periodo_baseline_inicio),
        periodo_baseline_fim=_data(periodo_baseline_fim),
        variante_a=sugestao.variante_a,
        variante_b=sugestao.variante_b,
        status=AdaptiveExperiment.STATUS_AGUARDANDO_APROVACAO,
        observacoes=observacoes,
    )


def listar_experimentos(portal=_TODOS):
    """Sem argumento, devolve todos. Com portal=None, só os globais."""
    qs = AdaptiveExperiment.objects.all()
    if portal is _TODOS:
        return qs
    return qs.filter(portal=portal)


def transicionar(experimento, status_novo):
    """Aplica a transição se ela for válida. Retorna False sem gravar quando não for."""
    if experimento is None or not pode_transicionar(experimento.status, status_novo):
        return False
    agora = now()
    experimento.status = status_novo
    campos = ['status']
    if status_novo == AdaptiveExperiment.STATUS_APROVADO:
        experimento.aprovado_em = agora
        campos.append('aprovado_em')
    elif status_novo == AdaptiveExperiment.STATUS_EXECUTANDO:
        experimento.iniciado_em = agora
        campos.append('iniciado_em')
    elif status_novo in (
        AdaptiveExperiment.STATUS_CONCLUIDO,
        AdaptiveExperiment.STATUS_CANCELADO,
    ):
        experimento.finalizado_em = agora
        campos.append('finalizado_em')
    experimento.save(update_fields=campos)
    return True


def _sugestao_valida(sugestao, area, portal):
    if not isinstance(sugestao, ExperimentSuggestion):
        return False
    if portal is not None and not isinstance(portal, Portal):
        return False
    if not isinstance(area, str) or not area.strip():
        return False
    textos = (
        sugestao.insight_id,
        sugestao.tipo,
        sugestao.titulo,
        sugestao.hipotese,
        sugestao.metrica_principal,
        sugestao.metrica_referencia,
        sugestao.variante_a,
        sugestao.variante_b,
    )
    if any(not isinstance(valor, str) or not valor.strip() for valor in textos):
        return False
    return sugestao.status == AdaptiveExperiment.STATUS_AGUARDANDO_APROVACAO


def _decimal(valor):
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float, str)):
        try:
            return Decimal(str(valor))
        except InvalidOperation:
            return None
    return None


def _inteiro(valor):
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        return 0
    return valor


def _data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None
