from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model


def _destinatarios_admin():
    emails = set()
    extra = getattr(settings, 'NOTIFY_EMAILS', [])
    if extra:
        emails.update(e for e in extra if e)
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        if user.email:
            emails.add(user.email)
    return list(emails)


def enviar_notificacao_admin(assunto, mensagem):
    destinatarios = _destinatarios_admin()
    if not destinatarios:
        return False
    remetente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@jiparana.local')
    try:
        send_mail(
            assunto,
            mensagem,
            remetente,
            destinatarios,
            fail_silently=False,
        )
        return True
    except Exception:
        return False


def notificar_comentario(comentario):
    noticia = comentario.noticia
    usuario = comentario.usuario
    assunto = f'[Ji-Paraná] Novo comentário: {noticia.titulo[:50]}'
    mensagem = (
        f'Novo comentário no portal {settings.SITE_NAME}\n\n'
        f'Notícia: {noticia.titulo}\n'
        f'Usuário: {usuario.get_username()}\n'
        f'Comentário:\n{comentario.texto}\n\n'
        f'---\nPainel: /painel/ | Admin: comentários'
    )
    return enviar_notificacao_admin(assunto, mensagem)


def notificar_curtida(curtida):
    noticia = curtida.noticia
    usuario = curtida.usuario
    assunto = f'[Ji-Paraná] Nova curtida: {noticia.titulo[:50]}'
    mensagem = (
        f'Nova curtida no portal {settings.SITE_NAME}\n\n'
        f'Notícia: {noticia.titulo}\n'
        f'Usuário: {usuario.get_username()}\n'
        f'Total de curtidas: {noticia.curtidas.count()}\n'
    )
    return enviar_notificacao_admin(assunto, mensagem)


def notificar_novo_envio(contribuicao):
    assunto = f'[Ji-Paraná] Novo envio para análise: {contribuicao.titulo[:50]}'
    midia = []
    if contribuicao.imagem:
        midia.append('foto')
    if contribuicao.video:
        midia.append('vídeo')
    mensagem = (
        f'Novo envio da comunidade\n\n'
        f'Título: {contribuicao.titulo}\n'
        f'Por: {contribuicao.nome} ({contribuicao.get_tipo_display()})\n'
        f'E-mail: {contribuicao.email}\n'
        f'Telefone: {contribuicao.telefone or "—"}\n'
        f'Mídia: {", ".join(midia) or "texto apenas"}\n\n'
        f'Analise em: /painel/'
    )
    return enviar_notificacao_admin(assunto, mensagem)
