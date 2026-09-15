from django.db.models import Q

from plataforma.models import AuditLog, EmailLog


def timeline_cliente(cliente):
    eventos = []
    if cliente.criado_em:
        eventos.append({'quando': cliente.criado_em, 'texto': 'Cliente criado'})
    for portal in cliente.portais.all():
        if portal.criado_em:
            eventos.append({'quando': portal.criado_em, 'texto': f'Portal criado ({portal.slug})'})
        for membro in portal.membros.select_related('usuario'):
            eventos.append({
                'quando': membro.criado_em,
                'texto': f'Usuário criado ({membro.usuario.username})',
            })
            if membro.usuario.last_login:
                eventos.append({
                    'quando': membro.usuario.last_login,
                    'texto': f'Login ({membro.usuario.username})',
                })
    for assinatura in cliente.assinaturas.select_related('plano'):
        if assinatura.iniciado_em:
            eventos.append({
                'quando': assinatura.iniciado_em,
                'texto': f'Pagamento aprovado ({assinatura.plano.nome})',
            })
        eventos.append({
            'quando': assinatura.criado_em,
            'texto': f'Assinatura {assinatura.get_status_display()}',
        })
    for mail in cliente.emails.all()[:40]:
        quando = mail.enviado_em or mail.criado_em
        if mail.status == EmailLog.STATUS_ENVIADO:
            texto = f'E-mail {mail.get_tipo_display()} enviado'
        else:
            texto = f'E-mail {mail.get_tipo_display()} {mail.get_status_display().lower()}'
        eventos.append({'quando': quando, 'texto': texto})
    for log in AuditLog.objects.filter(
        Q(portal__cliente=cliente) | Q(objeto_id=str(cliente.pk), objeto='Cliente')
    ).order_by('-criado_em')[:30]:
        eventos.append({'quando': log.criado_em, 'texto': log.acao.replace('_', ' ')})
    eventos = [e for e in eventos if e.get('quando')]
    eventos.sort(key=lambda e: e['quando'], reverse=True)
    vistos = set()
    unicos = []
    for evento in eventos:
        chave = (evento['quando'].replace(microsecond=0), evento['texto'])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(evento)
    return unicos[:40]
