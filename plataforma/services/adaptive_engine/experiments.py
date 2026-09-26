"""Sugestões de experimento a partir de insights já calculados.

Não executa teste, não grava banco e não altera o site.
O único status desta fase é aguardando_aprovacao.

Status reservados para fases futuras, ainda não implementados:
aprovado, rejeitado, executando, concluido, cancelado, inconclusivo.
"""
import logging
from dataclasses import asdict, dataclass

from plataforma.services.adaptive_engine.bottlenecks import AMOSTRA_MINIMA_GARGALO

logger = logging.getLogger(__name__)

STATUS_AGUARDANDO = 'aguardando_aprovacao'
_REFERENCIA = 'linha de base = período de 14 dias antes do início'
_AUSENTE = object()
_CONFIANCAS = {'baixa', 'media', 'alta'}
_ETAPAS = {
    ('baixa_passagem', 'funil_gratis'): 'click_subscribe → portal_created',
    ('baixa_passagem', 'funil_pago'): 'click_plan → initiate_checkout',
}
_TIPOS = {
    ('baixa_passagem', 'funil_gratis'): 'teste_de_fluxo',
    ('baixa_passagem', 'funil_pago'): 'teste_de_fluxo',
}
_VERBOS_INVESTIGACAO = ('investigar', 'analisar', 'testar', 'verificar')
_VERBOS_OBSERVACAO = ('monitorar', 'comparar')


@dataclass
class ExperimentSuggestion:
    id: str
    insight_id: str
    tipo: str
    titulo: str
    hipotese: str
    metrica_principal: str
    metrica_referencia: str
    amostra: int
    confianca: str
    status: str
    variante_a: str
    variante_b: str

    def como_dict(self):
        return asdict(self)


def pode_gerar_experimento(insight):
    """Decide se o insight pode virar sugestão. Não gera a sugestão."""
    try:
        campos = _campos(insight)
    except Exception:
        logger.debug('Insight ilegível ignorado na decisão de experimento.')
        return False
    if campos is None:
        return False
    if campos['amostra'] < AMOSTRA_MINIMA_GARGALO:
        return False
    if (campos['tipo'], campos['area']) not in _ETAPAS:
        return False
    if not _REFERENCIA:
        return False
    if _apenas_observacao(campos['acao']):
        return False
    return True


def sugerir_experimentos(insights):
    sugestoes = []
    for insight in list(insights or []):
        try:
            if not pode_gerar_experimento(insight):
                continue
            sugestoes.append(_montar(insight))
        except Exception:
            logger.debug('Insight ignorado ao sugerir experimento.')
            continue
    sugestoes.sort(key=lambda item: item.id)
    return sugestoes


def _campos(insight):
    obrigatorios = ('id', 'tipo', 'area', 'confianca', 'amostra')
    lidos = {nome: _ler(insight, nome) for nome in obrigatorios}
    if any(valor is _AUSENTE or valor in (None, '') for valor in lidos.values()):
        logger.debug('Insight malformado ignorado.')
        return None
    if lidos['confianca'] not in _CONFIANCAS:
        logger.debug('Insight sem confiança calculada ignorado.')
        return None
    if isinstance(lidos['amostra'], bool) or not isinstance(lidos['amostra'], int):
        logger.debug('Insight com amostra inválida ignorado.')
        return None
    acao = _ler(insight, 'acao_sugerida')
    if acao is _AUSENTE or not isinstance(acao, str):
        logger.debug('Insight sem ação investigável ignorado.')
        return None
    lidos['acao'] = acao
    return lidos


def _montar(insight):
    campos = _campos(insight)
    etapa = _ETAPAS[(campos['tipo'], campos['area'])]
    tipo = _TIPOS[(campos['tipo'], campos['area'])]
    hipotese = _ler(insight, 'hipotese')
    if not isinstance(hipotese, str) or 'hipótese' not in hipotese.lower():
        hipotese = 'Hipótese: a passagem nesta etapa pode merecer um teste controlado.'
    return ExperimentSuggestion(
        id=f"{campos['id']}:{tipo}",
        insight_id=campos['id'],
        tipo=tipo,
        titulo=_titulo(campos['area']),
        hipotese=hipotese,
        metrica_principal=etapa,
        metrica_referencia=_REFERENCIA,
        amostra=campos['amostra'],
        confianca=campos['confianca'],
        status=STATUS_AGUARDANDO,
        variante_a='Fluxo atual, sem alteração.',
        variante_b='Variação controlada nesta etapa, definida somente após aprovação humana.',
    )


def _titulo(area):
    if area == 'funil_pago':
        return 'Teste de fluxo entre plano e checkout'
    return 'Teste de fluxo na criação do portal'


def _apenas_observacao(acao):
    baixo = acao.lower()
    if any(verbo in baixo for verbo in _VERBOS_INVESTIGACAO):
        return False
    return any(verbo in baixo for verbo in _VERBOS_OBSERVACAO) or not baixo.strip()


def _ler(insight, campo):
    if isinstance(insight, dict):
        if campo not in insight:
            return _AUSENTE
        return insight[campo]
    if not hasattr(insight, campo):
        return _AUSENTE
    return getattr(insight, campo)
