"""Analytics do funil comercial. Somente escrita pública; leitura só no Master."""
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from uuid import UUID, uuid4

from django.conf import settings
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncHour
from django.utils.dateparse import parse_date
from django.utils.timezone import get_current_timezone, localdate, make_aware, now

from plataforma.models import AnalyticsEvent, AnalyticsSession, Portal
from plataforma.resolvers import is_local_or_platform_host

COOKIE_NAME = 'pup_aid'
TIPOS = frozenset({
    'page_view',
    'view_home',
    'view_plans',
    'click_plan',
    'click_subscribe',
    'initiate_checkout',
    'registration_start',
    'registration_complete',
    'portal_created',
    'purchase',
    'heartbeat',
})
# Nomes históricos. O Master não soma mais estes tipos numa fila só.
FUNIL = (
    ('view_home', 'Home'),
    ('view_plans', 'Planos'),
    ('click_plan', 'Clique em contratar'),
    ('initiate_checkout', 'Checkout'),
    ('registration_start', 'Cadastro'),
    ('purchase', 'Compra'),
)


def host_comercial(request):
    return is_local_or_platform_host(request.get_host())


def ativo_desde():
    minutos = int(getattr(settings, 'ANALYTICS_ACTIVE_MINUTES', 3) or 3)
    return now() - timedelta(minutes=max(1, minutos))


def _limpar_texto(valor, limite):
    return str(valor or '').strip()[:limite]


def _paths_equivalentes(path):
    path = _path_seguro(path)
    sem_barra = path.rstrip('/') or '/'
    com_barra = sem_barra if sem_barra == '/' else sem_barra + '/'
    return list({path, sem_barra, com_barra})


def _path_seguro(valor):
    bruto = _limpar_texto(valor, 200)
    if not bruto:
        return '/'
    if bruto.startswith('http://') or bruto.startswith('https://'):
        bruto = urlparse(bruto).path or '/'
    if not bruto.startswith('/'):
        bruto = '/' + bruto
    return bruto.split('?')[0][:200]


def _dispositivo(ua):
    texto = (ua or '').lower()
    if 'ipad' in texto or 'tablet' in texto:
        return AnalyticsSession.DISPOSITIVO_TABLET
    if 'mobi' in texto or 'android' in texto or 'iphone' in texto:
        return AnalyticsSession.DISPOSITIVO_MOBILE
    if texto:
        return AnalyticsSession.DISPOSITIVO_DESKTOP
    return AnalyticsSession.DISPOSITIVO_DESCONHECIDO


def _rotulo(uid):
    hexa = uid.hex.upper()
    letra = chr(65 + (int(hexa[0], 16) % 26))
    return f'{letra}{hexa[1:3]}'


def _uuid_cookie(request):
    bruto = (request.COOKIES.get(COOKIE_NAME) or '').strip()
    try:
        return UUID(bruto)
    except (ValueError, AttributeError, TypeError):
        return None


def classificar_path(path):
    path = _path_seguro(path)
    if path in {'/', ''}:
        return 'view_home'
    if path.startswith('/cadastro') or path.startswith('/criar-conta'):
        return 'registration_start'
    if path.startswith('/comece/') and path.count('/') >= 3:
        return 'initiate_checkout'
    if path.startswith('/comece'):
        return 'view_plans'
    return 'page_view'


def gravar_cookie(response, sessao):
    response.set_cookie(
        COOKIE_NAME,
        str(sessao.id),
        max_age=60 * 60 * 24 * 180,
        httponly=True,
        samesite='Lax',
        secure=not getattr(settings, 'DEBUG', False),
    )
    return response


def obter_ou_criar_sessao(request, path='/', extra=None):
    extra = extra or {}
    uid = _uuid_cookie(request)
    sessao = AnalyticsSession.objects.filter(pk=uid).first() if uid else None
    instante = now()
    if sessao is None:
        uid = uuid4()
        sessao = AnalyticsSession(
            id=uid,
            rotulo=_rotulo(uid),
            visto_em=instante,
            path_primeiro=_path_seguro(path),
            path_atual=_path_seguro(path),
            referrer=_limpar_texto(extra.get('referrer') or request.META.get('HTTP_REFERER'), 300),
            utm_source=_limpar_texto(extra.get('utm_source') or request.GET.get('utm_source'), 80),
            utm_medium=_limpar_texto(extra.get('utm_medium') or request.GET.get('utm_medium'), 80),
            utm_campaign=_limpar_texto(extra.get('utm_campaign') or request.GET.get('utm_campaign'), 120),
            utm_content=_limpar_texto(extra.get('utm_content') or request.GET.get('utm_content'), 120),
            utm_term=_limpar_texto(extra.get('utm_term') or request.GET.get('utm_term'), 120),
            fbclid=_limpar_texto(extra.get('fbclid') or request.GET.get('fbclid'), 200),
            fbp=_limpar_texto(extra.get('fbp'), 80),
            fbc=_limpar_texto(extra.get('fbc'), 200),
            dispositivo=_dispositivo(request.META.get('HTTP_USER_AGENT')),
        )
        sessao.save()
        return sessao, True
    campos = ['visto_em', 'path_atual']
    sessao.visto_em = instante
    sessao.path_atual = _path_seguro(path) or sessao.path_atual
    for campo in (
        'referrer', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
        'utm_term', 'fbclid', 'fbp', 'fbc',
    ):
        valor = _limpar_texto(extra.get(campo), 200 if campo in {'referrer', 'fbclid', 'fbc'} else 120)
        if valor and not getattr(sessao, campo):
            setattr(sessao, campo, valor)
            campos.append(campo)
    if not sessao.dispositivo or sessao.dispositivo == AnalyticsSession.DISPOSITIVO_DESCONHECIDO:
        sessao.dispositivo = _dispositivo(request.META.get('HTTP_USER_AGENT'))
        campos.append('dispositivo')
    sessao.save(update_fields=campos)
    return sessao, False


def _podar_antigos():
    dias = int(getattr(settings, 'ANALYTICS_RETENTION_DAYS', 90) or 90)
    limite = now() - timedelta(days=max(7, dias))
    AnalyticsEvent.objects.filter(criado_em__lt=limite).delete()
    AnalyticsSession.objects.filter(visto_em__lt=limite).delete()


def registrar_evento(request, tipo, path='/', extra=None, ref_externo='', portal=None):
    extra = extra or {}
    tipo = (tipo or '').strip()
    if tipo not in TIPOS or not host_comercial(request):
        return None
    path = _path_seguro(path or extra.get('path') or request.path)
    sessao, _ = obter_ou_criar_sessao(request, path, extra)
    if tipo == 'heartbeat':
        return sessao
    if tipo == 'page_view':
        derivado = classificar_path(path)
        if derivado != 'page_view':
            tipo = derivado
            # O script repete a abertura que o servidor já gravou. Uma visita
            # posterior continua contando, porque o servidor grava de novo.
            if AnalyticsEvent.objects.filter(
                sessao=sessao,
                tipo=tipo,
                path__in=_paths_equivalentes(path),
                criado_em__gte=now() - timedelta(seconds=120),
            ).exists():
                return sessao
    ref_externo = _limpar_texto(ref_externo or extra.get('eid') or extra.get('order_id'), 80)
    if ref_externo and AnalyticsEvent.objects.filter(tipo=tipo, ref_externo=ref_externo).exists():
        return sessao
    recente = now() - timedelta(seconds=4)
    if AnalyticsEvent.objects.filter(
        sessao=sessao, tipo=tipo, path=path, criado_em__gte=recente,
    ).exists():
        return sessao
    payload = {}
    for chave in ('plano', 'valor', 'nome_plano'):
        if extra.get(chave) not in (None, ''):
            payload[chave] = extra[chave]
    AnalyticsEvent.objects.create(
        sessao=sessao,
        portal=portal,
        tipo=tipo,
        path=path,
        extra=payload,
        ref_externo=ref_externo,
    )
    if AnalyticsEvent.objects.count() % 250 == 0:
        _podar_antigos()
    return sessao


def anexar_page_view(request, response, tipo=None):
    if response.status_code >= 400 or not host_comercial(request):
        return response
    sessao = registrar_evento(request, tipo or 'page_view', path=request.path)
    if sessao:
        gravar_cookie(response, sessao)
    return response


def registrar_compra(assinatura, request=None):
    if assinatura is None:
        return None
    extra = {
        'plano': getattr(assinatura.plano, 'codigo', ''),
        'nome_plano': getattr(assinatura.plano, 'nome', ''),
        'valor': str(getattr(assinatura.plano, 'preco_mensal', '')),
        'order_id': assinatura.kiwify_order_id,
    }
    if request is not None and host_comercial(request):
        return registrar_evento(
            request,
            'purchase',
            path='/comece/',
            extra=extra,
            ref_externo=assinatura.kiwify_order_id,
            portal=assinatura.portal,
        )
    if AnalyticsEvent.objects.filter(tipo='purchase', ref_externo=assinatura.kiwify_order_id).exists():
        return None
    uid = uuid4()
    sessao = AnalyticsSession.objects.create(
        id=uid,
        rotulo=_rotulo(uid),
        visto_em=now(),
        path_primeiro='/comece/',
        path_atual='/comece/',
        portal=assinatura.portal,
    )
    AnalyticsEvent.objects.create(
        sessao=sessao,
        portal=assinatura.portal,
        tipo='purchase',
        path='/comece/',
        extra=extra,
        ref_externo=assinatura.kiwify_order_id or '',
    )
    return sessao


def _dia_aware(dia, fim=False):
    dt = make_aware(datetime.combine(dia, time.min), get_current_timezone())
    if fim:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def periodo_de_params(params):
    chave = (params.get('periodo') or 'hoje').strip()
    hoje = localdate()
    if chave == 'ontem':
        inicio = hoje - timedelta(days=1)
        return chave, _dia_aware(inicio), _dia_aware(inicio, fim=True)
    if chave == '7d':
        return chave, _dia_aware(hoje - timedelta(days=6)), _dia_aware(hoje, fim=True)
    if chave == '30d':
        return chave, _dia_aware(hoje - timedelta(days=29)), _dia_aware(hoje, fim=True)
    if chave == 'custom':
        de = parse_date(params.get('de') or '') or hoje
        ate = parse_date(params.get('ate') or '') or hoje
        if ate < de:
            de, ate = ate, de
        return chave, _dia_aware(de), _dia_aware(ate, fim=True)
    return 'hoje', _dia_aware(hoje), _dia_aware(hoje, fim=True)


def portal_filtrado(params):
    bruto = (params.get('portal') or '').strip()
    if not bruto:
        return None
    try:
        return Portal.objects.filter(pk=int(bruto)).first()
    except (TypeError, ValueError):
        return None


def _qs_eventos(inicio, fim, portal=None):
    qs = AnalyticsEvent.objects.filter(criado_em__gte=inicio, criado_em__lte=fim)
    if portal is not None:
        qs = qs.filter(Q(portal=portal) | Q(sessao__portal=portal))
    return qs


def _sessoes_unicas(qs, tipo):
    return qs.filter(tipo=tipo).values('sessao_id').distinct().count()


def _ids(qs):
    return set(qs.values_list('sessao_id', flat=True).distinct())


def _funil_sequencial(passos):
    """Cada etapa só conta sessões que também passaram pela anterior."""
    funil = []
    anterior = None
    entrada = 0
    for tipo, label, ids in passos:
        ids = set(ids)
        atual = ids if anterior is None else ids & anterior
        qtd = len(atual)
        if anterior is None:
            entrada = qtd
        pct_total = round((qtd / entrada) * 100, 1) if entrada else 0
        pct_ant = round((qtd / len(anterior)) * 100, 1) if anterior else 100.0
        abandono = max(0, len(anterior) - qtd) if anterior is not None else 0
        funil.append({
            'tipo': tipo, 'label': label, 'quantidade': qtd,
            'pct_total': pct_total, 'pct_anterior': pct_ant, 'abandono': abandono,
        })
        anterior = atual
    return funil


def montar_dashboard(params):
    periodo, inicio, fim = periodo_de_params(params)
    portal = portal_filtrado(params)
    eventos = _qs_eventos(inicio, fim, portal)
    sessoes = AnalyticsSession.objects.filter(criado_em__gte=inicio, criado_em__lte=fim)
    if portal is not None:
        sessoes = sessoes.filter(Q(portal=portal) | Q(eventos__portal=portal)).distinct()
    ativos_qs = AnalyticsSession.objects.filter(visto_em__gte=ativo_desde())
    if portal is not None:
        ativos_qs = ativos_qs.filter(Q(portal=portal) | Q(eventos__portal=portal)).distinct()

    cliques_gratis = _ids(eventos.filter(tipo='click_subscribe', path__startswith='/app/comecar'))
    cliques_pagos = _ids(eventos.filter(tipo='click_plan'))
    checkouts_ids = _ids(eventos.filter(tipo='initiate_checkout'))
    portais_ids = _ids(eventos.filter(tipo='portal_created'))
    entrada_direta_ids = checkouts_ids - cliques_pagos
    portais_sem_clique_ids = portais_ids - cliques_gratis
    funil_gratis = _funil_sequencial([
        ('click_subscribe', 'Criar meu portal', cliques_gratis),
        ('portal_created', 'Portal criado', portais_ids),
    ])
    funil_pago = _funil_sequencial([
        ('click_plan', 'Plano pago escolhido', cliques_pagos),
        ('initiate_checkout', 'Checkout', checkouts_ids),
    ])
    funil_comparacao = _funil_sequencial([
        ('view_plans', 'Visita a /comece/', _ids(eventos.filter(tipo='view_plans'))),
    ])
    funil = funil_pago

    compras_qs = eventos.filter(tipo='purchase')
    sessoes_compra = _ids(compras_qs)
    sessoes_com_jornada = _ids(eventos.exclude(tipo='purchase'))
    compras_orfas_ids = sessoes_compra - sessoes_com_jornada
    receita = Decimal('0')
    for item in compras_qs.values_list('extra', flat=True):
        try:
            receita += Decimal(str((item or {}).get('valor') or '0'))
        except (InvalidOperation, TypeError):
            continue

    visitantes = sessoes.count() or eventos.values('sessao_id').distinct().count()
    compras_total = len(sessoes_compra)
    taxa = round((compras_total / visitantes) * 100, 2) if visitantes else 0

    por_hora = list(
        eventos.annotate(hora=TruncHour('criado_em')).values('hora').annotate(
            n=Count('id'), unicos=Count('sessao_id', distinct=True),
        ).order_by('hora')
    )
    origens = {}
    dispositivos = {}
    campanhas = {}
    for sessao in sessoes:
        origens[sessao.origem_label()] = origens.get(sessao.origem_label(), 0) + 1
        disp = sessao.get_dispositivo_display()
        dispositivos[disp] = dispositivos.get(disp, 0) + 1
        if sessao.utm_campaign:
            campanhas[sessao.utm_campaign] = campanhas.get(sessao.utm_campaign, 0) + 1

    paginas = list(
        eventos.filter(tipo__in=['page_view', 'view_home', 'view_plans', 'initiate_checkout', 'registration_start'])
        .values('path').annotate(
            pageviews=Count('id'),
            unicos=Count('sessao_id', distinct=True),
            ultima=Max('criado_em'),
        ).order_by('-unicos')[:20]
    )
    max_pag = max((p['unicos'] for p in paginas), default=1) or 1
    for item in paginas:
        item['pct'] = round((item['unicos'] / max_pag) * 100)

    max_hora = max((h['unicos'] for h in por_hora), default=1) or 1
    for item in por_hora:
        item['pct'] = round((item['unicos'] / max_hora) * 100)

    def _barras(mapa):
        teto = max(mapa.values() or [1]) or 1
        return [
            {'label': k, 'n': v, 'pct': round((v / teto) * 100)}
            for k, v in sorted(mapa.items(), key=lambda x: -x[1])[:8]
        ]

    return {
        'periodo': periodo,
        'inicio': inicio,
        'fim': fim,
        'portal': portal,
        'visitantes': visitantes,
        'ativos': ativos_qs.count(),
        'pageviews': eventos.filter(
            tipo__in=['page_view', 'view_home', 'view_plans', 'initiate_checkout', 'registration_start'],
        ).count(),
        'view_plans': _sessoes_unicas(eventos, 'view_plans'),
        'clicks': eventos.filter(tipo__in=['click_plan', 'click_subscribe']).values('sessao_id').distinct().count(),
        'clicks_gratis': len(cliques_gratis),
        'clicks_pagos': len(cliques_pagos),
        'checkouts': len(checkouts_ids),
        'entrada_direta': len(entrada_direta_ids),
        'portais_gratis': len(portais_ids),
        'portais_sem_clique': len(portais_sem_clique_ids),
        'cadastros': _sessoes_unicas(eventos, 'registration_complete') or _sessoes_unicas(eventos, 'registration_start'),
        'compras': compras_total,
        'compras_orfas': len(compras_orfas_ids),
        'receita': receita,
        'taxa': taxa,
        'funil': funil,
        'funil_gratis': funil_gratis,
        'funil_pago': funil_pago,
        'funil_comparacao': funil_comparacao,
        'por_hora': por_hora,
        'eventos_hora': por_hora,
        'origens': _barras(origens),
        'dispositivos': _barras(dispositivos),
        'campanhas': _barras(campanhas),
        'paginas': paginas,
        'compras_lista': list(compras_qs.select_related('sessao', 'portal')[:20]),
        'sessoes': list(sessoes.order_by('-visto_em')[:40]),
        'ativos_lista': list(ativos_qs.order_by('-visto_em')[:30]),
        'portais': list(Portal.objects.order_by('nome').only('id', 'nome', 'slug')),
    }


def sessoes_ativas(portal=None):
    qs = AnalyticsSession.objects.filter(visto_em__gte=ativo_desde())
    if portal is not None:
        qs = qs.filter(Q(portal=portal) | Q(eventos__portal=portal)).distinct()
    return qs.order_by('-visto_em')
