from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.timezone import now
import logging

from noticias.models import Categoria
from plataforma.models import Assinatura, Cliente, EmailLog, Membership, Plano, Portal
from plataforma.services.acesso import enviar_acesso, enviar_boas_vindas_gratuito
from plataforma.security import log_audit
from plataforma.services.kiwify import extrair_assinatura_kiwify, extrair_cliente
from plataforma.slugs import gerar_slug_provisorio

User = get_user_model()
logger = logging.getLogger('plataforma.onboarding')


def resolver_plano(dados_kiwify):
    plano = None
    if dados_kiwify.get('plan_id'):
        plano = Plano.objects.filter(ativo=True, kiwify_plan_id=dados_kiwify['plan_id']).first()
    if plano is None and dados_kiwify.get('product_id'):
        plano = Plano.objects.filter(ativo=True, kiwify_product_id=dados_kiwify['product_id']).first()
    if plano is None:
        plano = (
            Plano.objects.filter(ativo=True)
            .exclude(preco_mensal=0)
            .order_by('ordem', 'preco_mensal')
            .first()
        )
    if plano is None:
        plano = Plano.objects.filter(codigo='basico').first() or Plano.objects.order_by('id').first()
    return plano


def _username_de_email(email):
    base = slugify(email.split('@')[0])[:20] or 'admin'
    candidato = base
    n = 2
    while User.objects.filter(username=candidato).exists():
        candidato = f'{base}{n}'
        n += 1
    return candidato


def _assinatura_gratuita_para_upgrade(cliente):
    return (
        Assinatura.objects.filter(
            cliente=cliente,
            origem=Assinatura.ORIGEM_GRATUITA,
            status=Assinatura.STATUS_ATIVA,
        )
        .select_related('portal', 'plano', 'cliente')
        .order_by('-criado_em')
        .first()
    )


def _aplicar_upgrade_pago(assinatura, dados_sub, plano, request=None):
    assinatura.plano = plano
    assinatura.origem = Assinatura.ORIGEM_KIWIFY
    assinatura.status = Assinatura.STATUS_ATIVA
    if dados_sub.get('subscription_id'):
        assinatura.kiwify_subscription_id = dados_sub['subscription_id']
    if dados_sub.get('order_id'):
        assinatura.kiwify_order_id = dados_sub['order_id']
    if dados_sub.get('transaction_id'):
        assinatura.kiwify_transaction_id = str(dados_sub['transaction_id'])[:80]
    assinatura.iniciado_em = assinatura.iniciado_em or dados_sub.get('start_date') or now()
    if dados_sub.get('next_payment'):
        assinatura.proximo_vencimento = dados_sub['next_payment']
    assinatura.cancelado_em = None
    assinatura.bloqueado_em = None
    assinatura.save()
    portal = assinatura.portal
    portal.status = Portal.STATUS_ATIVO
    portal.pagamento_status = Portal.PAGAMENTO_PAGO
    portal.plano = plano
    portal.save(update_fields=['status', 'pagamento_status', 'plano'])
    _sincronizar_portal_pagamento(portal, assinatura)
    log_audit(
        request, 'upgrade_plano', objeto='Assinatura', objeto_id=assinatura.pk,
        portal=portal, detalhes={'plano': plano.codigo if plano else ''},
    )
    try:
        from plataforma.services.analytics import registrar_compra
        registrar_compra(assinatura)
    except Exception:
        logger.exception('Falha ao registrar upgrade no analytics')
    return {
        'criado': False,
        'upgrade': True,
        'portal': portal,
        'cliente': assinatura.cliente,
        'assinatura': assinatura,
        'usuario': None,
    }


def plano_gratuito():
    plano = Plano.objects.filter(ativo=True, codigo='gratuito').first()
    if plano is None:
        plano = Plano.objects.filter(ativo=True, preco_mensal=0).order_by('ordem', 'id').first()
    return plano


@transaction.atomic
def provisionar_portal_gratuito(*, nome, email, slug, cidade, estado, senha='', usuario=None, request=None):
    """Cria Cliente, Portal, User e Membership no plano gratuito, sem Kiwify."""
    email = (email or '').strip().lower()
    if not email:
        raise ValueError('E-mail obrigatório.')
    plano = plano_gratuito()
    if plano is None:
        raise ValueError('Plano gratuito indisponível.')

    cliente, _ = Cliente.objects.get_or_create(
        email=email,
        defaults={'nome': nome[:160] or email.split('@')[0], 'status': Cliente.STATUS_ATIVO},
    )
    if cliente.status != Cliente.STATUS_ATIVO:
        cliente.status = Cliente.STATUS_ATIVO
        cliente.save(update_fields=['status'])

    portal = Portal.objects.create(
        nome=nome[:120],
        slug=slug,
        cidade=(cidade or 'Brasil')[:80],
        estado=(estado or 'BR')[:50],
        email=email,
        cliente=cliente,
        cliente_nome=cliente.nome,
        cliente_email=cliente.email,
        plano=plano,
        status=Portal.STATUS_ATIVO,
        pagamento_status=Portal.PAGAMENTO_GRATUITO,
        slogan='Notícias da sua cidade',
        descricao=f'Portal de notícias de {(cidade or "sua cidade")}.',
        setup_concluido=True,
    )
    Categoria.all_objects.get_or_create(
        portal=portal, slug='geral', defaults={'nome': 'Geral'},
    )

    user = usuario or User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create_user(
            username=_username_de_email(email),
            email=email,
            password=senha or get_random_string(12),
            first_name=(nome or '')[:30],
        )
    Membership.objects.get_or_create(
        usuario=user,
        portal=portal,
        defaults={'papel': Membership.PAPEL_ADMIN, 'ativo': True},
    )
    assinatura = Assinatura.objects.create(
        cliente=cliente,
        portal=portal,
        plano=plano,
        status=Assinatura.STATUS_ATIVA,
        origem=Assinatura.ORIGEM_GRATUITA,
        iniciado_em=now(),
    )
    log_audit(
        request, 'onboarding_gratuito', objeto='Assinatura', objeto_id=assinatura.pk,
        portal=portal, detalhes={'email': cliente.email, 'slug': portal.slug},
    )
    log_audit(request, 'primeiro_acesso', objeto='Portal', objeto_id=portal.pk, portal=portal)
    try:
        enviar_boas_vindas_gratuito(user, portal, request=request, cliente=cliente)
    except Exception:
        logger.exception('Falha ao disparar o e-mail do cadastro gratuito')
    return {
        'criado': True,
        'portal': portal,
        'cliente': cliente,
        'assinatura': assinatura,
        'usuario': user,
    }


def _localizar_assinatura(dados):
    if dados.get('subscription_id'):
        existente = Assinatura.objects.filter(
            kiwify_subscription_id=dados['subscription_id'],
        ).select_related('portal', 'cliente', 'plano').first()
        if existente:
            return existente
    if dados.get('order_id'):
        return (
            Assinatura.objects.filter(kiwify_order_id=dados['order_id'])
            .select_related('portal', 'cliente', 'plano')
            .first()
        )
    return None


def _sincronizar_portal_pagamento(portal, assinatura):
    mapa = {
        Assinatura.STATUS_ATIVA: Portal.PAGAMENTO_PAGO,
        Assinatura.STATUS_PENDENTE: Portal.PAGAMENTO_PENDENTE,
        Assinatura.STATUS_ATRASADA: Portal.PAGAMENTO_ATRASADO,
        Assinatura.STATUS_AGUARDANDO: Portal.PAGAMENTO_PENDENTE,
        Assinatura.STATUS_CANCELADA: Portal.PAGAMENTO_ATRASADO,
        Assinatura.STATUS_BLOQUEADA: Portal.PAGAMENTO_ATRASADO,
    }
    portal.pagamento_status = mapa.get(assinatura.status, portal.pagamento_status)
    portal.plano = assinatura.plano
    portal.cliente = assinatura.cliente
    portal.cliente_nome = assinatura.cliente.nome
    portal.cliente_email = assinatura.cliente.email
    portal.save(update_fields=[
        'pagamento_status', 'plano', 'cliente', 'cliente_nome', 'cliente_email',
    ])


def _enviar_acesso(usuario, portal, request=None, cliente=None):
    return enviar_acesso(
        usuario,
        portal,
        request=request,
        tipo=EmailLog.TIPO_ONBOARDING,
        cliente=cliente,
    )


@transaction.atomic
def provisionar_pagamento_aprovado(payload, request=None):
    dados_cli = extrair_cliente(payload)
    dados_sub = extrair_assinatura_kiwify(payload)
    if not dados_cli['email']:
        raise ValueError('Webhook sem e-mail do comprador (Customer.email).')

    existente = _localizar_assinatura(dados_sub)
    if existente:
        return atualizar_assinatura_aprovada(existente, dados_sub, request=request)

    cliente_previo = Cliente.objects.filter(email=dados_cli['email']).first()
    if cliente_previo is not None:
        gratuita = _assinatura_gratuita_para_upgrade(cliente_previo)
        if gratuita is not None:
            plano = resolver_plano(dados_sub)
            return _aplicar_upgrade_pago(gratuita, dados_sub, plano, request=request)

    cliente, _ = Cliente.objects.get_or_create(
        email=dados_cli['email'],
        defaults={
            'nome': dados_cli['nome'],
            'telefone': dados_cli['telefone'],
            'status': Cliente.STATUS_ATIVO,
        },
    )
    if cliente.status != Cliente.STATUS_ATIVO:
        cliente.status = Cliente.STATUS_ATIVO
        cliente.save(update_fields=['status'])
    if dados_cli['telefone'] and not cliente.telefone:
        cliente.telefone = dados_cli['telefone']
        cliente.save(update_fields=['telefone'])

    plano = resolver_plano(dados_sub)
    nome_portal = 'Portal em configuração'
    portal = None
    for tentativa in range(8):
        slug = gerar_slug_provisorio()
        try:
            with transaction.atomic():
                portal = Portal.objects.create(
                    nome=nome_portal,
                    slug=slug,
                    cidade=dados_cli['cidade'][:80],
                    estado=dados_cli['estado'][:50],
                    email=dados_cli['email'],
                    telefone=dados_cli['telefone'][:20],
                    cliente=cliente,
                    cliente_nome=cliente.nome,
                    cliente_email=cliente.email,
                    plano=plano,
                    status=Portal.STATUS_ATIVO,
                    pagamento_status=Portal.PAGAMENTO_PAGO,
                    slogan='Notícias da sua cidade',
                    descricao=f'Portal de notícias de {dados_cli["cidade"]}.',
                    setup_concluido=False,
                )
            break
        except IntegrityError:
            if tentativa >= 7:
                raise
    if portal is None:
        raise IntegrityError('Não foi possível gerar um slug provisório único.')
    Categoria.all_objects.get_or_create(
        portal=portal, slug='geral', defaults={'nome': 'Geral'},
    )

    user = User.objects.filter(email__iexact=dados_cli['email']).first()
    if user is None:
        user = User.objects.create_user(
            username=_username_de_email(dados_cli['email']),
            email=dados_cli['email'],
            password=get_random_string(12),
            first_name=dados_cli['nome'][:30],
        )

    Membership.objects.get_or_create(
        usuario=user,
        portal=portal,
        defaults={'papel': Membership.PAPEL_ADMIN, 'ativo': True},
    )

    assinatura = Assinatura.objects.create(
        cliente=cliente,
        portal=portal,
        plano=plano,
        status=Assinatura.STATUS_ATIVA,
        origem=Assinatura.ORIGEM_KIWIFY,
        kiwify_subscription_id=dados_sub['subscription_id'],
        kiwify_order_id=dados_sub['order_id'],
        kiwify_transaction_id=str(dados_sub['transaction_id'])[:80],
        iniciado_em=dados_sub['start_date'] or now(),
        proximo_vencimento=dados_sub['next_payment'],
    )
    log_audit(
        request,
        'onboarding_aprovado',
        objeto='Assinatura',
        objeto_id=assinatura.pk,
        portal=portal,
        detalhes={'email': cliente.email, 'slug': portal.slug},
    )
    usuario = user
    portal_ref = portal
    cliente_ref = cliente
    req = request

    def _enviar():
        _enviar_acesso(usuario, portal_ref, request=req, cliente=cliente_ref)

    transaction.on_commit(_enviar)
    try:
        from plataforma.services.analytics import registrar_compra
        registrar_compra(assinatura)
    except Exception:
        logger.exception('Falha ao registrar evento de compra no analytics')
    return {
        'criado': True,
        'portal': portal,
        'cliente': cliente,
        'assinatura': assinatura,
        'usuario': user,
    }


@transaction.atomic
def atualizar_assinatura_aprovada(assinatura, dados_sub, request=None):
    assinatura.status = Assinatura.STATUS_ATIVA
    if dados_sub.get('subscription_id'):
        assinatura.kiwify_subscription_id = dados_sub['subscription_id']
    if dados_sub.get('order_id'):
        assinatura.kiwify_order_id = dados_sub['order_id']
    if dados_sub.get('transaction_id'):
        assinatura.kiwify_transaction_id = str(dados_sub['transaction_id'])[:80]
    if dados_sub.get('next_payment'):
        assinatura.proximo_vencimento = dados_sub['next_payment']
    if dados_sub.get('start_date') and not assinatura.iniciado_em:
        assinatura.iniciado_em = dados_sub['start_date']
    assinatura.bloqueado_em = None
    assinatura.cancelado_em = None
    assinatura.save()
    portal = assinatura.portal
    portal.status = Portal.STATUS_ATIVO
    portal.save(update_fields=['status'])
    _sincronizar_portal_pagamento(portal, assinatura)
    log_audit(
        request, 'assinatura_reativada', objeto='Assinatura',
        objeto_id=assinatura.pk, portal=portal,
    )
    return {
        'criado': False,
        'portal': portal,
        'cliente': assinatura.cliente,
        'assinatura': assinatura,
        'usuario': None,
    }


@transaction.atomic
def marcar_pendente(payload, request=None):
    dados_sub = extrair_assinatura_kiwify(payload)
    assinatura = _localizar_assinatura(dados_sub)
    if assinatura is None:
        return None
    assinatura.status = Assinatura.STATUS_PENDENTE
    assinatura.save(update_fields=['status', 'atualizado_em'])
    _sincronizar_portal_pagamento(assinatura.portal, assinatura)
    return assinatura


@transaction.atomic
def marcar_atrasada(payload, request=None):
    dados_sub = extrair_assinatura_kiwify(payload)
    assinatura = _localizar_assinatura(dados_sub)
    if assinatura is None:
        return None
    assinatura.status = Assinatura.STATUS_ATRASADA
    assinatura.save(update_fields=['status', 'atualizado_em'])
    _sincronizar_portal_pagamento(assinatura.portal, assinatura)
    return assinatura


@transaction.atomic
def cancelar_ou_bloquear(payload, request=None, bloquear=True):
    dados_sub = extrair_assinatura_kiwify(payload)
    assinatura = _localizar_assinatura(dados_sub)
    if assinatura is None:
        return None
    agora = now()
    assinatura.status = Assinatura.STATUS_BLOQUEADA if bloquear else Assinatura.STATUS_CANCELADA
    assinatura.cancelado_em = agora
    if bloquear:
        assinatura.bloqueado_em = agora
    assinatura.save()
    portal = assinatura.portal
    portal.status = Portal.STATUS_BLOQUEADO
    portal.save(update_fields=['status'])
    _sincronizar_portal_pagamento(portal, assinatura)
    log_audit(
        request, 'assinatura_bloqueada', objeto='Assinatura',
        objeto_id=assinatura.pk, portal=portal,
    )
    return assinatura


@transaction.atomic
def master_definir_status_portal(portal, ativo, request=None):
    portal.status = Portal.STATUS_ATIVO if ativo else Portal.STATUS_BLOQUEADO
    portal.save(update_fields=['status'])
    assinatura = portal.assinatura_atual()
    if assinatura:
        if ativo:
            assinatura.status = Assinatura.STATUS_ATIVA
            assinatura.bloqueado_em = None
        else:
            assinatura.status = Assinatura.STATUS_BLOQUEADA
            assinatura.bloqueado_em = now()
        assinatura.save()
        _sincronizar_portal_pagamento(portal, assinatura)
    log_audit(
        request,
        'portal_ativar' if ativo else 'portal_bloquear',
        objeto='Portal',
        objeto_id=portal.pk,
        portal=portal,
    )
    return portal


@transaction.atomic
def master_alterar_plano(portal, plano, request=None):
    portal.plano = plano
    portal.save(update_fields=['plano'])
    assinatura = portal.assinatura_atual()
    if assinatura:
        assinatura.plano = plano
        assinatura.save(update_fields=['plano', 'atualizado_em'])
    log_audit(
        request, 'portal_plano', objeto='Portal', objeto_id=portal.pk,
        portal=portal, detalhes={'plano': plano.codigo},
    )
    return portal
