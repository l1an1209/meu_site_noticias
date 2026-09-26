"""Insights determinísticos a partir de métricas e gargalos já calculados.

Não consulta o banco. Não cria ranking. A confiança é a do gargalo.
Hipótese permanece hipótese.
"""
from dataclasses import asdict, dataclass


_ORDEM = {
    ('baixa_passagem', 'funil_gratis'): 1,
    ('baixa_passagem', 'funil_pago'): 2,
    ('checkout_direto', 'checkout'): 3,
    ('queda_de_trafego', 'trafego'): 4,
    ('variacao_de_conversao', 'funil_gratis'): 5,
    ('variacao_de_conversao', 'funil_pago'): 6,
}

_TERMOS_CAUSAIS = (
    'porque', 'causou', 'causado', 'problema', 'anúncio', 'anuncio',
    'seo', 'algoritmo', 'falha', 'bug',
)
_ACOES_PROIBIDAS = (
    'mudar o preço', 'mudar preço', 'alterar o preço', 'alterar preço',
    'alterar o checkout', 'mudar o checkout', 'criar campanha',
    'pausar anúncio', 'pausar anuncio', 'mudar a home', 'alterar a home',
    'alterar o cta',
)


@dataclass
class Insight:
    id: str
    tipo: str
    area: str
    titulo: str
    resumo: str
    evidencias: list
    amostra: int
    confianca: str
    variacao: float | None
    hipotese: str
    acao_sugerida: str

    def como_dict(self):
        return asdict(self)


def gerar(metrics, gargalos):
    metricas = metrics or {}
    insights = []
    for gargalo in list(gargalos or []):
        insight = _traduzir(metricas, gargalo)
        if insight is not None:
            insights.append(insight)
    insights.sort(key=lambda item: (_ORDEM.get((item.tipo, item.area), 99), item.id))
    return insights


def _traduzir(metricas, gargalo):
    tipo = gargalo.get('tipo')
    area = gargalo.get('area')
    if (tipo, area) not in _ORDEM:
        return None
    if gargalo.get('confianca') == 'baixa':
        return None
    amostra = gargalo.get('amostra') or 0
    if amostra < 30:
        return None
    if tipo == 'baixa_passagem' and area == 'funil_gratis':
        return _passagem_gratis(metricas, gargalo)
    if tipo == 'baixa_passagem' and area == 'funil_pago':
        return _passagem_pago(metricas, gargalo)
    if tipo == 'checkout_direto':
        return _checkout(metricas, gargalo)
    if tipo == 'queda_de_trafego':
        return _trafego(gargalo)
    if tipo == 'variacao_de_conversao':
        return _conversao(gargalo)
    return None


def _passagem_gratis(metricas, gargalo):
    taxa = gargalo.get('taxa_observada')
    cliques = _metrica(metricas, 'funil_gratis', 'cliques')
    criados = _metrica(metricas, 'funil_gratis', 'portal_no_fluxo')
    if cliques is None:
        cliques = gargalo.get('amostra')
    if criados is None:
        criados = _estimado(taxa, cliques)
    return _montar(
        gargalo,
        id='funil_gratis_baixa_passagem',
        titulo='Baixa passagem no funil gratuito',
        resumo=(
            'Foi observada baixa passagem entre o clique para criação do portal '
            f'e a criação efetiva do portal. A passagem observada foi de {_fmt_taxa(taxa)}.'
        ),
        evidencias=[
            {'metrica': 'click_subscribe', 'valor': cliques},
            {'metrica': 'portal_created', 'valor': criados},
            {'metrica': 'taxa', 'valor': taxa},
        ],
        hipotese=(
            'Hipótese: pode existir algum ponto da jornada entre o interesse '
            'e a criação efetiva que merece investigação.'
        ),
        acao_sugerida=(
            'Investigar as etapas entre o clique e a criação do portal '
            'e observar o comportamento antes de qualquer alteração.'
        ),
    )


def _passagem_pago(metricas, gargalo):
    taxa = gargalo.get('taxa_observada')
    cliques = _metrica(metricas, 'funil_pago', 'cliques')
    checkouts = _metrica(metricas, 'funil_pago', 'checkout_no_fluxo')
    if cliques is None:
        cliques = gargalo.get('amostra')
    if checkouts is None:
        checkouts = _estimado(taxa, cliques)
    return _montar(
        gargalo,
        id='funil_pago_baixa_passagem',
        titulo='Baixa passagem entre plano e checkout',
        resumo=(
            'A passagem observada entre a seleção do plano e o checkout '
            f'desse fluxo foi de {_fmt_taxa(taxa)}.'
        ),
        evidencias=[
            {'metrica': 'click_plan', 'valor': cliques},
            {'metrica': 'initiate_checkout', 'valor': checkouts},
            {'metrica': 'taxa', 'valor': taxa},
        ],
        hipotese=(
            'Hipótese: o comportamento entre a seleção do plano e o checkout '
            'pode merecer investigação antes de qualquer alteração comercial.'
        ),
        acao_sugerida='Analisar o caminho entre a seleção do plano e o início do checkout.',
    )


def _checkout(metricas, gargalo):
    taxa = gargalo.get('taxa_observada')
    diretas = _metrica(metricas, 'checkout_direto', 'sessoes')
    if diretas is None:
        diretas = _estimado(taxa, gargalo.get('amostra'))
    return _montar(
        gargalo,
        id='checkout_direto',
        titulo='Concentração de entradas diretas no checkout',
        resumo=(
            'Uma parcela relevante das sessões de checkout não possui um evento '
            f'de seleção de plano rastreado antes. A proporção observada foi de {_fmt_taxa(taxa)}.'
        ),
        evidencias=[
            {'metrica': 'checkout_direto', 'valor': diretas},
            {'metrica': 'checkouts', 'valor': gargalo.get('amostra')},
            {'metrica': 'proporcao', 'valor': taxa},
        ],
        hipotese=(
            'Hipótese: pode haver uma rota que chega ao checkout sem o evento '
            'de seleção de plano, ou uma lacuna de rastreamento.'
        ),
        acao_sugerida=(
            'Investigar a origem dessas sessões e verificar se o rastreamento '
            'representa o fluxo observado.'
        ),
    )


def _trafego(gargalo):
    variacao = gargalo.get('variacao')
    return _montar(
        gargalo,
        id='queda_de_trafego',
        titulo='Queda relevante de sessões',
        resumo=(
            'O período atual apresentou queda de '
            f'{_fmt_percentual(variacao)} nas sessões em relação à janela anterior equivalente.'
        ),
        evidencias=[
            {'metrica': 'sessoes_atual', 'valor': gargalo.get('valor_atual')},
            {'metrica': 'sessoes_anterior', 'valor': gargalo.get('valor_anterior')},
            {'metrica': 'variacao', 'valor': variacao},
        ],
        hipotese='Hipótese: a origem da variação pode merecer investigação.',
        acao_sugerida=(
            'Comparar origem, dispositivo, campanha e distribuição '
            'entre os dois períodos.'
        ),
    )


def _conversao(gargalo):
    area = gargalo.get('area')
    etapa = 'o funil gratuito' if area == 'funil_gratis' else 'o funil pago'
    return _montar(
        gargalo,
        id=f'variacao_conversao_{area}',
        titulo='Variação relevante de conversão',
        resumo=(
            f'A taxa de passagem em {etapa} variou {_fmt_pontos(gargalo.get("variacao"))} '
            'pontos percentuais em relação ao período anterior. '
            f'Período atual: {_fmt_taxa(gargalo.get("valor_atual"))}. '
            f'Período anterior: {_fmt_taxa(gargalo.get("valor_anterior"))}.'
        ),
        evidencias=[
            {'metrica': 'taxa_atual', 'valor': gargalo.get('valor_atual')},
            {'metrica': 'taxa_anterior', 'valor': gargalo.get('valor_anterior')},
            {'metrica': 'variacao', 'valor': gargalo.get('variacao')},
        ],
        hipotese=(
            'Hipótese: o comportamento pode merecer investigação para ver '
            'quais etapas ou segmentos acompanham a alteração.'
        ),
        acao_sugerida='Comparar funil, origem e dispositivo entre os períodos.',
    )


def _montar(gargalo, id, titulo, resumo, evidencias, hipotese, acao_sugerida):
    _recusar_texto(resumo, hipotese, acao_sugerida, titulo)
    return Insight(
        id=id,
        tipo=gargalo.get('tipo'),
        area=gargalo.get('area'),
        titulo=titulo,
        resumo=resumo,
        evidencias=evidencias,
        amostra=gargalo.get('amostra'),
        confianca=gargalo.get('confianca'),
        variacao=gargalo.get('variacao'),
        hipotese=hipotese,
        acao_sugerida=acao_sugerida,
    )


def _metrica(metricas, bloco, chave):
    caixa = metricas.get(bloco) or {}
    item = caixa.get(chave) or {}
    if isinstance(item, dict):
        return item.get('valor')
    return None


def _estimado(taxa, amostra):
    if taxa is None or not amostra:
        return None
    return int(round(taxa * amostra))


def _fmt_taxa(valor):
    if valor is None:
        return 'sem taxa'
    return _fmt_percentual(valor)


def _fmt_percentual(valor):
    if valor is None:
        return 'sem variação'
    pontos = abs(valor) * 100
    if abs(pontos - round(pontos)) < 0.05:
        return f'{int(round(pontos))}%'
    return f'{pontos:.2f}%'.replace('.', ',')


def _fmt_pontos(valor):
    if valor is None:
        return 'sem variação'
    pontos = abs(valor) * 100
    if abs(pontos - round(pontos)) < 0.05:
        return str(int(round(pontos)))
    return f'{pontos:.2f}'.replace('.', ',')


def _recusar_texto(*textos):
    baixo = ' '.join(textos).lower()
    if any(termo in baixo for termo in _TERMOS_CAUSAIS):
        raise ValueError('Insight atribui causa.')
    if any(termo in baixo for termo in _ACOES_PROIBIDAS):
        raise ValueError('Insight sugere alteração comercial.')
