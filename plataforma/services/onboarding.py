from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.timezone import now

from noticias.models import Categoria
from noticias.services.email_notify import enviar_notificacao_admin
from plataforma.models import Assinatura, Cliente, Membership, Plano, Portal
from plataforma.security import log_audit
from plataforma.services.kiwify import extrair_assinatura_kiwify, extrair_cliente
from plataforma.slugs import gerar_slug_portal

User = get_user_model()


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


def _enviar_acesso(usuario, senha, portal, gerou_senha):
    host = portal.host_previsto
    linhas = [
        f'Olá, {usuario.get_short_name() or usuario.username}.',
        '',
        f'Seu portal {portal.nome} está pronto.',
        f'Endereço futuro: https://{host}/',
        f'Painel: https://{host}/app/',
        f'Usuário: {usuario.username}',
    ]
    if gerou_senha:
        linhas.append(f'Senha temporária: {senha}')
        linhas.append('Altere a senha no primeiro acesso em /senha/alterar/')
    else:
        linhas.append('Use a senha da sua conta existente.')
    linhas.extend(['', 'Se o DNS ainda não estiver no ar, acesse pelo Host configurado no ambiente de testes.'])
    enviar_notificacao_admin(
        f'[{portal.nome}] Acesso ao seu portal',
        '\n'.join(linhas),
        portal,
    )
    if usuario.email:
        from django.conf import settings
        from django.core.mail import send_mail
        send_mail(
            f'Acesso ao {portal.nome}',
            '\n'.join(linhas),
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@plataforma.local'),
            [usuario.email],
            fail_silently=True,
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
    nome_portal = dados_sub.get('product_name') or f"Portal de {dados_cli['cidade']}"
    slug = gerar_slug_portal(nome_portal, dados_cli['email'])

    portal = Portal.objects.create(
        nome=nome_portal[:120],
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
    )
    Categoria.all_objects.get_or_create(
        portal=portal, slug='geral', defaults={'nome': 'Geral'},
    )

    user = User.objects.filter(email__iexact=dados_cli['email']).first()
    senha = None
    gerou = False
    if user is None:
        senha = get_random_string(12)
        user = User.objects.create_user(
            username=_username_de_email(dados_cli['email']),
            email=dados_cli['email'],
            password=senha,
            first_name=dados_cli['nome'][:30],
        )
        gerou = True

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
    _enviar_acesso(user, senha, portal, gerou)
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
