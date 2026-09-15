"""Saúde operacional. Não envia e-mail automaticamente."""
from pathlib import Path

from django.conf import settings
from django.db import connection

from plataforma.models import Assinatura, EmailLog, WebhookEvent
from plataforma.services.email import diagnosticar_smtp


def _item(nivel, titulo, detalhe=''):
    return {'nivel': nivel, 'titulo': titulo, 'detalhe': detalhe}


def verificar_saude():
    itens = []
    itens.append(_item('ok', 'Aplicação', 'O painel Master está respondendo.'))

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        itens.append(_item('ok', 'Banco de dados', connection.vendor))
    except Exception:
        itens.append(_item('falha', 'Banco de dados', 'Não foi possível consultar o banco.'))

    smtp = diagnosticar_smtp(conectar=False)
    itens.append(_item(smtp['nivel'], 'SMTP', smtp['detalhe']))

    secret = getattr(settings, 'KIWIFY_WEBHOOK_SECRET', '') or ''
    if secret:
        itens.append(_item('ok', 'Kiwify / webhook', 'Segredo de webhook configurado.'))
    else:
        itens.append(_item('atencao', 'Kiwify / webhook', 'KIWIFY_WEBHOOK_SECRET vazio neste ambiente.'))

    falhas_wh = WebhookEvent.objects.filter(status=WebhookEvent.STATUS_ERRO).count()
    if falhas_wh:
        itens.append(_item('falha', 'Webhooks com erro', f'{falhas_wh} evento(s) falharam.'))

    static_ok = bool(getattr(settings, 'STATIC_ROOT', None) or getattr(settings, 'STATIC_URL', None))
    itens.append(
        _item('ok' if static_ok else 'atencao', 'Arquivos estáticos', settings.STATIC_URL or 'STATIC_URL ausente')
    )

    media = Path(getattr(settings, 'MEDIA_ROOT', '') or '')
    if media:
        try:
            media.mkdir(parents=True, exist_ok=True)
            writable = media.is_dir()
        except OSError:
            writable = False
        itens.append(
            _item('ok' if writable else 'atencao', 'Mídia', str(media) if writable else 'MEDIA_ROOT inacessível')
        )

    emails_falha = EmailLog.objects.filter(status=EmailLog.STATUS_FALHOU).count()
    if emails_falha:
        itens.append(_item('falha', 'E-mails com falha', f'{emails_falha} envio(s) falharam.'))

    atrasadas = Assinatura.objects.filter(status=Assinatura.STATUS_ATRASADA).count()
    if atrasadas:
        itens.append(_item('atencao', 'Assinaturas atrasadas', str(atrasadas)))

    return itens


def problemas_operacao():
    from django.urls import reverse

    from plataforma.models import Assinatura, Cliente, EmailLog, WebhookEvent

    problemas = []
    emails_acesso = EmailLog.objects.filter(
        tipo__in=[EmailLog.TIPO_ONBOARDING, EmailLog.TIPO_REENVIO],
        status=EmailLog.STATUS_FALHOU,
    )
    n_acesso = emails_acesso.count()
    if n_acesso:
        problemas.append({
            'nivel': 'falha',
            'texto': f'{n_acesso} cliente(s) não receberam acesso',
            'acao': 'Ver clientes',
            'url': reverse('master_clientes'),
        })
    n_wh = WebhookEvent.objects.filter(status=WebhookEvent.STATUS_ERRO).count()
    if n_wh:
        problemas.append({
            'nivel': 'falha',
            'texto': f'{n_wh} webhook(s) falharam',
            'acao': 'Ver webhooks',
            'url': reverse('master_webhooks'),
        })
    n_pend = Assinatura.objects.filter(
        status__in=[Assinatura.STATUS_PENDENTE, Assinatura.STATUS_AGUARDANDO],
    ).count()
    if n_pend:
        problemas.append({
            'nivel': 'atencao',
            'texto': f'{n_pend} pagamento(s) pendente(s)',
            'acao': 'Ver assinaturas',
            'url': reverse('master_assinaturas') + '?status=pagamento_pendente',
        })
    n_atr = Assinatura.objects.filter(status=Assinatura.STATUS_ATRASADA).count()
    if n_atr:
        problemas.append({
            'nivel': 'atencao',
            'texto': f'{n_atr} assinatura(s) atrasada(s)',
            'acao': 'Ver assinaturas',
            'url': reverse('master_assinaturas') + '?status=atrasada',
        })
    n_mail = EmailLog.objects.filter(status=EmailLog.STATUS_FALHOU).count()
    if n_mail and not n_acesso:
        problemas.append({
            'nivel': 'atencao',
            'texto': f'{n_mail} e-mail(s) falharam',
            'acao': 'Ver configurações',
            'url': reverse('master_configuracoes'),
        })
    n_block = Cliente.objects.filter(status=Cliente.STATUS_INATIVO).count()
    if n_block:
        problemas.append({
            'nivel': 'atencao',
            'texto': f'{n_block} cliente(s) inativo(s)',
            'acao': 'Ver clientes',
            'url': reverse('master_clientes') + '?status=inativo',
        })
    return problemas
