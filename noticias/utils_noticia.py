from .models import Noticia


def criar_noticia_de_contribuicao(contrib):
    noticia = Noticia.objects.create(
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
    return noticia
