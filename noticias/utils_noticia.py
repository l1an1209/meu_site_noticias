from .models import Noticia, NoticiaImagem


def criar_noticia_de_contribuicao(contrib):
    noticia = Noticia.objects.create(
        portal=contrib.portal,
        titulo=contrib.titulo,
        conteudo=contrib.conteudo,
        categoria=contrib.categoria,
        autor=contrib.nome,
        resumo=contrib.conteudo[:280],
    )
    updated = []
    if contrib.imagem:
        noticia.imagem.save(contrib.imagem.name, contrib.imagem, save=False)
        updated.append('imagem')
    if contrib.video:
        noticia.video.save(contrib.video.name, contrib.video, save=False)
        updated.append('video')
    if updated:
        noticia.save(update_fields=updated)

    ordem = 0
    for extra in contrib.fotos.all():
        if not extra.imagem:
            continue
        foto = NoticiaImagem(noticia=noticia, ordem=ordem)
        foto.imagem.save(extra.imagem.name, extra.imagem, save=False)
        foto.save()
        ordem += 1
    return noticia


def anexar_fotos_envio(contribuicao, arquivos):
    ordem = contribuicao.fotos.count()
    from .models import ContribuicaoImagem
    for arquivo in arquivos:
        if not arquivo:
            continue
        ContribuicaoImagem.objects.create(
            contribuicao=contribuicao,
            imagem=arquivo,
            ordem=ordem,
        )
        ordem += 1
