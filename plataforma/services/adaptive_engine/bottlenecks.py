"""Detecção determinística de gargalos, só a partir das métricas da 1.2.

Mesma entrada produz a mesma saída. Amostra abaixo do piso não vira gargalo.
O texto descreve o padrão observado e não atribui causa.
"""
from plataforma.services.adaptive_engine.metrics import AMOSTRA_MINIMA, calcular

# Piso igual ao da 1.2. Abaixo disso a taxa existe, mas o detector não emite.
AMOSTRA_MINIMA_GARGALO = AMOSTRA_MINIMA

# A partir daqui a confiança sobe de média para alta. 100 sessões no denominador
# ainda é uma leitura inicial, não uma prova.
AMOSTRA_CONFIANCA_ALTA = 100

# Passagem menor que 20% entre a etapa de entrada e a seguinte.
# Os exemplos da fase (6,67% e 12,5%) ficam abaixo; 20% ou mais não dispara.
LIMIAR_BAIXA_PASSAGEM = 0.20

# Metade ou mais dos checkouts sem click_plan rastreado.
# Abaixo disso a entrada direta existe, mas não concentra o fluxo.
LIMIAR_CHECKOUT_DIRETO = 0.50

# Queda relativa de sessões de 30% ou mais contra a janela anterior.
# Uma oscilação de cerca de 10% permanece dentro do esperado.
LIMIAR_QUEDA_TRAFEGO = -0.30

# Diferença absoluta entre taxas, em pontos (0.15 = 15 pontos percentuais).
# Compara só quando os dois períodos já passaram do piso de amostra.
LIMIAR_VARIACAO_CONVERSAO = 0.15

_TERMOS_CAUSAIS = (
    'porque', 'causou', 'causado', 'causa', 'problema', 'anúncio', 'anuncio',
    'seo', 'algoritmo', 'falha', 'bug',
)


def detectar(params):
    metricas = calcular(params)
    gargalos = []
    gargalos.extend(_baixa_passagem(
        metricas, 'gratis_clique_para_portal', 'funil_gratis',
        'click_subscribe → portal_created',
        'Foi observada uma passagem baixa entre o clique em criar o portal e o portal criado.',
    ))
    gargalos.extend(_baixa_passagem(
        metricas, 'pago_clique_para_checkout', 'funil_pago',
        'click_plan → initiate_checkout',
        'Foi observada uma passagem baixa entre a escolha do plano e o checkout desse fluxo.',
    ))
    gargalos.extend(_checkout_direto(metricas))
    gargalos.extend(_queda_trafego(metricas))
    gargalos.extend(_variacao_conversao(metricas))
    gargalos.sort(key=lambda item: (item['area'], item['tipo'], item['etapa']))
    return {
        'gargalos': gargalos,
        'compras': _compras(metricas),
    }


def _baixa_passagem(metricas, chave, area, etapa, descricao):
    taxa = metricas['conversoes'][chave]
    if taxa['estado'] != 'ok' or taxa['valor'] is None:
        return []
    if taxa['valor'] >= LIMIAR_BAIXA_PASSAGEM:
        return []
    return [_item(
        tipo='baixa_passagem',
        area=area,
        etapa=etapa,
        descricao=descricao,
        taxa_observada=taxa['valor'],
        variacao=None,
        amostra=taxa['amostra'],
        amostra_anterior=None,
        valor_atual=taxa['valor'],
        valor_anterior=None,
        limiar_usado=LIMIAR_BAIXA_PASSAGEM,
    )]


def _checkout_direto(metricas):
    proporcao = metricas['checkout_direto']['proporcao']
    if proporcao['estado'] != 'ok' or proporcao['valor'] is None:
        return []
    if proporcao['valor'] < LIMIAR_CHECKOUT_DIRETO:
        return []
    return [_item(
        tipo='checkout_direto',
        area='checkout',
        etapa='initiate_checkout sem click_plan',
        descricao=(
            'Foi detectada uma concentração de sessões que abriram o checkout '
            'sem um click_plan rastreado. O sinal pede investigação posterior.'
        ),
        taxa_observada=proporcao['valor'],
        variacao=None,
        amostra=proporcao['amostra'],
        amostra_anterior=None,
        valor_atual=proporcao['valor'],
        valor_anterior=None,
        limiar_usado=LIMIAR_CHECKOUT_DIRETO,
    )]


def _queda_trafego(metricas):
    atual = metricas['aquisicao']['sessoes']
    anterior = metricas['comparacao']['aquisicao']['sessoes']
    if atual['estado'] != 'ok' or anterior['estado'] != 'ok':
        return []
    if not anterior['valor']:
        return []
    variacao = round((atual['valor'] - anterior['valor']) / anterior['valor'], 4)
    if variacao > LIMIAR_QUEDA_TRAFEGO:
        return []
    return [_item(
        tipo='queda_de_trafego',
        area='trafego',
        etapa='sessoes → periodo anterior',
        descricao='Foi observada uma queda de sessões em relação ao período anterior de mesma duração.',
        taxa_observada=None,
        variacao=variacao,
        amostra=atual['amostra'],
        amostra_anterior=anterior['amostra'],
        valor_atual=atual['valor'],
        valor_anterior=anterior['valor'],
        limiar_usado=LIMIAR_QUEDA_TRAFEGO,
    )]


def _variacao_conversao(metricas):
    pares = (
        ('gratis_clique_para_portal', 'funil_gratis', 'click_subscribe → portal_created'),
        ('pago_clique_para_checkout', 'funil_pago', 'click_plan → initiate_checkout'),
    )
    achados = []
    for chave, area, etapa in pares:
        atual = metricas['conversoes'][chave]
        anterior = metricas['comparacao']['conversoes'][chave]
        if atual['estado'] != 'ok' or anterior['estado'] != 'ok':
            continue
        if atual['valor'] is None or anterior['valor'] is None:
            continue
        variacao = round(atual['valor'] - anterior['valor'], 4)
        if abs(variacao) < LIMIAR_VARIACAO_CONVERSAO:
            continue
        achados.append(_item(
            tipo='variacao_de_conversao',
            area=area,
            etapa=etapa,
            descricao=(
                'Foi observada uma variação na taxa de passagem em relação '
                'ao período anterior de mesma duração.'
            ),
            taxa_observada=atual['valor'],
            variacao=variacao,
            amostra=min(atual['amostra'], anterior['amostra']),
            amostra_anterior=anterior['amostra'],
            valor_atual=atual['valor'],
            valor_anterior=anterior['valor'],
            limiar_usado=LIMIAR_VARIACAO_CONVERSAO,
        ))
    return achados


def _compras(metricas):
    sessoes = metricas['aquisicao']['sessoes']
    compras = metricas['compras']['sessoes']
    if sessoes['estado'] != 'ok':
        return {'estado': 'amostra_insuficiente', 'gargalo': False}
    if not compras['valor']:
        return {'estado': 'sem_compra_observada', 'gargalo': False}
    return {'estado': 'com_compra', 'gargalo': False}


def _item(**dados):
    dados['confianca'] = _confianca(dados['amostra'])
    _recusar_causa(dados['descricao'])
    return dados


def _confianca(amostra):
    if amostra >= AMOSTRA_CONFIANCA_ALTA:
        return 'alta'
    if amostra >= AMOSTRA_MINIMA_GARGALO:
        return 'media'
    return 'baixa'


def _recusar_causa(texto):
    baixo = texto.lower()
    if any(termo in baixo for termo in _TERMOS_CAUSAIS):
        raise ValueError('Descrição de gargalo atribui causa.')
