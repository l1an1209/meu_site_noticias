"""Regra única de publicidade da rede. Templates não decidem pelo código do plano."""
from django.core.cache import cache
from django.db.models import Sum

from plataforma.models import ConfiguracaoMonetizacao, Plano, Portal

CACHE_CFG = 'monetizacao_cfg'
PREFIXOS_PRIVADOS = ('/app/', '/master/', '/admin/')
# ID de certificação publicado pelo Google para linhas DIRECT do AdSense.
CERTIFICACAO_GOOGLE = 'f08c47fec0942fa0'


def limpar_cache_monetizacao():
    cache.delete(CACHE_CFG)


def configuracao_monetizacao():
    cfg = cache.get(CACHE_CFG)
    if cfg is None:
        cfg = ConfiguracaoMonetizacao.obter()
        cache.set(CACHE_CFG, cfg, 30)
    return cfg


def plano_e_gratuito(plano):
    if plano is None:
        return False
    return plano.preco_mensal == 0


def portal_deve_exibir_publicidade(portal):
    if portal is None or portal.status != Portal.STATUS_ATIVO:
        return False
    cfg = configuracao_monetizacao()
    if not cfg.ativa:
        return False
    modo = portal.publicidade_modo or Portal.PUBLICIDADE_HERDAR
    if modo == Portal.PUBLICIDADE_INATIVA:
        return False
    if modo == Portal.PUBLICIDADE_ATIVA:
        return True
    plano = portal.plano
    if plano is None:
        return False
    if plano_e_gratuito(plano):
        return bool(cfg.publicidade_gratuito)
    return bool(cfg.publicidade_pago)


def _pagina_publica(request):
    if request is None:
        return False
    path = request.path or '/'
    return not any(path.startswith(prefixo) for prefixo in PREFIXOS_PRIVADOS)


def publisher_ads_txt(publisher_id):
    bruto = (publisher_id or '').strip()
    baixo = bruto.lower()
    if baixo.startswith('ca-pub-'):
        return 'pub-' + bruto[7:]
    if baixo.startswith('pub-'):
        return 'pub-' + bruto[4:]
    return ''


def linha_ads_txt_rede():
    pub = publisher_ads_txt(configuracao_monetizacao().publisher_id)
    if not pub:
        return ''
    return f'google.com, {pub}, DIRECT, {CERTIFICACAO_GOOGLE}\n'


def linha_ads_txt(portal):
    if not portal_deve_exibir_publicidade(portal):
        return ''
    return linha_ads_txt_rede()


def payload_publicidade(portal, request=None):
    vazio = {
        'exibir': False,
        'script': '',
        'publisher_id': '',
        'provedor': '',
        'posicoes': [],
    }
    if not _pagina_publica(request) or not portal_deve_exibir_publicidade(portal):
        return vazio
    cfg = configuracao_monetizacao()
    script = (cfg.codigo_script or '').strip()
    publisher = (cfg.publisher_id or '').strip()
    if not script and not publisher:
        return vazio
    return {
        'exibir': True,
        'script': script,
        'publisher_id': publisher,
        'provedor': cfg.provedor,
        'posicoes': cfg.posicoes_permitidas(),
    }


def resumo_rede():
    ativos = Portal.objects.filter(status=Portal.STATUS_ATIVO).select_related('plano')
    gratuitos = ativos.filter(plano__codigo='gratuito').count()
    pagos = ativos.exclude(plano__preco_mensal=0).count()
    com_publicidade = sum(1 for portal in ativos if portal.should_show_ads)
    from noticias.models import Noticia
    pageviews = Noticia.all_objects.aggregate(n=Sum('visualizacoes'))['n'] or 0
    por_portal = list(
        Portal.objects.filter(status=Portal.STATUS_ATIVO)
        .annotate(pageviews=Sum('noticias__visualizacoes'))
        .order_by('-pageviews', 'nome')
        .values('id', 'nome', 'slug', 'pageviews')[:12]
    )
    return {
        'portais_ativos': ativos.count(),
        'portais_gratuitos': gratuitos,
        'portais_pagos': pagos,
        'portais_com_publicidade': com_publicidade,
        'pageviews_rede': pageviews,
        'pageviews_por_portal': por_portal,
        'planos_ativos': Plano.objects.filter(ativo=True).count(),
    }
