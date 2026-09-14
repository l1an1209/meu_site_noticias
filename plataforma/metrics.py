from noticias.models import Anuncio, Contribuicao, ContribuicaoImagem, Noticia, NoticiaImagem
from plataforma.models import Portal


def _add(total, field):
    if not field:
        return total
    try:
        return total + int(field.size or 0)
    except Exception:
        return total


def storage_bytes_portal(portal: Portal) -> int:
    total = 0
    total = _add(total, portal.logo)
    total = _add(total, portal.favicon)
    total = _add(total, portal.imagem_compartilhamento)
    for n in Noticia.all_objects.filter(portal=portal).only('imagem', 'video'):
        total = _add(total, n.imagem)
        total = _add(total, n.video)
    for img in NoticiaImagem.objects.filter(noticia__portal=portal):
        total = _add(total, img.imagem)
    for c in Contribuicao.all_objects.filter(portal=portal).only('imagem', 'video'):
        total = _add(total, c.imagem)
        total = _add(total, c.video)
    for img in ContribuicaoImagem.objects.filter(contribuicao__portal=portal):
        total = _add(total, img.imagem)
    for a in Anuncio.all_objects.filter(portal=portal).only('imagem'):
        total = _add(total, a.imagem)
    return total


def format_mb(num_bytes):
    return round((num_bytes or 0) / (1024 * 1024), 2)
