"""Primeiro acesso do portal novo. Usa AuditLog; não cria outro cadastro."""
from urllib.parse import quote

from django.urls import reverse

from noticias.models import Categoria, Noticia
from plataforma.models import AuditLog
from plataforma.urls_portal import url_publica_portal

MARCA = 'primeiro_acesso'
IDENTIDADE = 'primeiro_identidade'
CATEGORIAS = 'primeiro_categorias'
VIU = 'primeiro_viu'
COMPARTILHOU = 'primeiro_compartilhou'

SUGESTOES = (
    ('Notícias', 'noticias'),
    ('Política', 'politica'),
    ('Economia', 'economia'),
    ('Esportes', 'esportes'),
    ('Cultura', 'cultura'),
    ('Entretenimento', 'entretenimento'),
)

LIBERADAS = {
    'app_aparencia',
    'app_categorias',
    'app_categoria_nova',
    'app_categoria_editar',
    'app_categoria_excluir',
    'app_noticia_nova',
    'app_noticia_editar',
    'app_ativar',
}


def _tem(portal, acao):
    return AuditLog.objects.filter(portal=portal, acao=acao).exists()


def primeiro_acesso_aberto(portal):
    if portal is None or not _tem(portal, MARCA):
        return False
    return not _tem(portal, COMPARTILHOU)


def etapa_primeiro_acesso(portal):
    if not primeiro_acesso_aberto(portal):
        return None
    if not _tem(portal, IDENTIDADE):
        return 'identidade'
    if not _tem(portal, CATEGORIAS):
        return 'categorias'
    if not Noticia.all_objects.filter(portal=portal).exists():
        return 'noticia'
    if not _tem(portal, VIU):
        return 'ver'
    return 'compartilhar'


def destino_etapa(etapa):
    return {
        'identidade': 'app_aparencia',
        'categorias': 'app_categorias',
        'noticia': 'app_noticia_nova',
        'ver': 'app_ativar',
        'compartilhar': 'app_ativar',
    }.get(etapa or '', 'app_home')


def garantir_categoria_padrao(portal):
    if Categoria.all_objects.filter(portal=portal).exists():
        return
    Categoria.all_objects.create(portal=portal, nome='Notícias', slug='noticias')


def adicionar_sugestao(portal, slug):
    item = next((par for par in SUGESTOES if par[1] == slug), None)
    if item is None:
        return
    Categoria.all_objects.get_or_create(
        portal=portal, slug=item[1], defaults={'nome': item[0]},
    )


def noticia_guia(portal):
    return Noticia.all_objects.filter(portal=portal).order_by('id').first()


def url_noticia_publica(portal, noticia):
    base = (url_publica_portal(portal) or '').rstrip('/')
    if not base or noticia is None:
        return ''
    return base + reverse('detalhe', args=[noticia.pk])


def url_whatsapp(portal, noticia):
    link = url_noticia_publica(portal, noticia)
    if not link:
        return ''
    texto = f'Confira esta notícia no {portal.nome}: {noticia.titulo} {link}'
    return 'https://wa.me/?text=' + quote(texto)


def progresso(portal):
    etapa = etapa_primeiro_acesso(portal)
    noticias = Noticia.all_objects.filter(portal=portal).exists()
    itens = (
        ('identidade', 'Identidade', _tem(portal, IDENTIDADE)),
        ('categorias', 'Categorias', _tem(portal, CATEGORIAS)),
        ('noticia', 'Primeira notícia', noticias),
        ('publicar', 'Publicar', noticias),
        ('ver', 'Ver portal', _tem(portal, VIU)),
        ('compartilhar', 'Compartilhar', _tem(portal, COMPARTILHOU)),
    )
    return etapa, itens
