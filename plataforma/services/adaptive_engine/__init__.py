"""Adaptive Engine: leitura, métricas, gargalos, insights, IA, sugestões e persistência."""
from plataforma.services.adaptive_engine.ai import analisar, preparar_contexto
from plataforma.services.adaptive_engine.bottlenecks import detectar
from plataforma.services.adaptive_engine.experiments import (
    ExperimentSuggestion,
    pode_gerar_experimento,
    sugerir_experimentos,
)
from plataforma.services.adaptive_engine.insights import Insight, gerar
from plataforma.services.adaptive_engine.leitura import ler
from plataforma.services.adaptive_engine.metrics import calcular
from plataforma.services.adaptive_engine.persistence import (
    criar_experimento,
    listar_experimentos,
    pode_transicionar,
    transicionar,
)

__all__ = [
    'ler', 'calcular', 'detectar', 'gerar', 'Insight',
    'preparar_contexto', 'analisar',
    'ExperimentSuggestion', 'sugerir_experimentos', 'pode_gerar_experimento',
    'criar_experimento', 'listar_experimentos', 'pode_transicionar', 'transicionar',
]
