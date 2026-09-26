"""Adaptive Engine: leitura, métricas, gargalos, insights e IA consultiva."""
from plataforma.services.adaptive_engine.ai import analisar, preparar_contexto
from plataforma.services.adaptive_engine.bottlenecks import detectar
from plataforma.services.adaptive_engine.insights import Insight, gerar
from plataforma.services.adaptive_engine.leitura import ler
from plataforma.services.adaptive_engine.metrics import calcular

__all__ = [
    'ler', 'calcular', 'detectar', 'gerar', 'Insight',
    'preparar_contexto', 'analisar',
]
