import os
import sys
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import migrations, models

import plataforma.models


SLUG_LEGADO = 'noticiasjiparana'
SLUG_TESTE = 'portalbeta'

# Identidade pública que estava em settings.py (um único site).
LEGADO = {
    'nome': 'Notícias Ji-Paraná',
    'cidade': 'Ji-Paraná',
    'estado': 'RO',
    'regiao': 'Ji-Paraná e região',
    'slogan': 'Notícias em tempo real',
    'tagline': 'Notícias Ji-Paraná e região — em tempo real',
    'descricao': (
        'Notícias Ji-Paraná e região em tempo real. Informação local, lojas e comunidade '
        'com conteúdo revisado antes de publicar.'
    ),
    'latitude': -10.8854,
    'longitude': -61.9516,
    'cor_primaria': '#0d9488',
    'cor_secundaria': '#1a365d',
    'cor_destaque': '#ea580c',
    'seo_title': 'Notícias Ji-Paraná — Notícias em tempo real',
    'seo_description': (
        'Notícias Ji-Paraná e região em tempo real. Informação local, lojas e comunidade '
        'com conteúdo revisado antes de publicar.'
    ),
    'adsense_client_id': 'ca-pub-5451545777538942',
    'texto_rodape': (
        'Notícias Ji-Paraná e região — em tempo real. '
        'Conteúdo revisado para moradores e comércios locais.'
    ),
    'facebook': '',
    'instagram': '',
    'youtube': '',
    'twitter': '',
    'tiktok': '',
}

BETA = {
    'nome': 'Portal Beta',
    'slug': SLUG_TESTE,
    'cidade': 'Campinas',
    'estado': 'SP',
    'regiao': 'Campinas e região',
    'slogan': 'Laboratório da plataforma',
    'tagline': 'Identidade visual distinta do portal legado',
    'descricao': 'Portal de testes com cores, SEO, contato e rodapé próprios.',
    'email': 'contato@portalbeta.test',
    'telefone': '(19) 3333-0000',
    'whatsapp': '5511999000000',
    'endereco': 'Av. Teste, 100 — Campinas/SP',
    'facebook': 'https://facebook.com/portalbeta',
    'instagram': 'https://instagram.com/portalbeta',
    'youtube': 'https://youtube.com/@portalbeta',
    'twitter': '',
    'tiktok': '',
    'cor_primaria': '#6d28d9',
    'cor_secundaria': '#111827',
    'cor_destaque': '#f59e0b',
    'seo_title': 'Portal Beta — outra cidade, outra marca',
    'seo_description': 'SEO exclusivo do Portal Beta para Campinas e a plataforma.',
    'adsense_client_id': '',
    'texto_rodape': 'Rodapé exclusivo do Portal Beta.',
    'latitude': -22.9056,
    'longitude': -47.0608,
    'status': 'ativo',
    'pagamento_status': 'cortesia',
}


def _em_teste():
    return 'test' in sys.argv or os.environ.get('PYTEST_CURRENT_TEST')


def _png(rgb, size=48):
    from PIL import Image

    buf = BytesIO()
    Image.new('RGB', (size, size), rgb).save(buf, format='PNG')
    return buf.getvalue()


def _anexar_se_vazio(portal, campo, filename, content):
    if getattr(portal, campo):
        return
    getattr(portal, campo).save(filename, ContentFile(content), save=False)


def _logo_legado_bytes():
    candidatos = [
        Path(settings.BASE_DIR) / 'static' / 'img' / 'logo.png',
        Path(settings.BASE_DIR) / 'static' / 'img' / 'favicon.png',
    ]
    for path in candidatos:
        if path.is_file():
            return path.read_bytes()
    return _png((13, 148, 136), 64)


def aplicar_identidade(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    Portal = apps.get_model('plataforma', 'Portal')
    plano = Plano.objects.filter(codigo='inicial').first()

    legado = Portal.objects.filter(slug=SLUG_LEGADO).first()
    if legado is None:
        legado = Portal(slug=SLUG_LEGADO, plano_id=getattr(plano, 'pk', None), status='ativo')
    for campo, valor in LEGADO.items():
        setattr(legado, campo, valor)
    if (legado.email or '').endswith(('@plataforma.local', '@noticias-jiparana.local')):
        legado.email = ''
    if not _em_teste():
        _anexar_se_vazio(legado, 'logo', 'logo.png', _logo_legado_bytes())
        _anexar_se_vazio(legado, 'favicon', 'favicon.png', _png((26, 54, 93), 32))
    legado.save()

    beta, created = Portal.objects.get_or_create(
        slug=SLUG_TESTE,
        defaults={**BETA, 'plano_id': getattr(plano, 'pk', None)},
    )
    if not created:
        for campo, valor in BETA.items():
            if campo == 'slug':
                continue
            setattr(beta, campo, valor)
        if plano and beta.plano_id is None:
            beta.plano_id = plano.pk
    if not _em_teste():
        _anexar_se_vazio(beta, 'logo', 'logo.png', _png((109, 40, 217), 64))
        _anexar_se_vazio(beta, 'favicon', 'favicon.png', _png((245, 158, 11), 32))
    beta.save()


def reverter(apps, schema_editor):
    Portal = apps.get_model('plataforma', 'Portal')
    Portal.objects.filter(slug=SLUG_TESTE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0001_portal_fk'),
        ('noticias', '0013_seed_default_portal'),
    ]

    operations = [
        migrations.AddField(
            model_name='portal',
            name='adsense_client_id',
            field=models.CharField(
                blank=True,
                help_text='Ex.: ca-pub-123. Vazio = não carrega o script do AdSense.',
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='portal',
            name='cor_destaque',
            field=models.CharField(default='#ea580c', max_length=7),
        ),
        migrations.AddField(
            model_name='portal',
            name='cor_primaria',
            field=models.CharField(default='#0d9488', max_length=7),
        ),
        migrations.AddField(
            model_name='portal',
            name='cor_secundaria',
            field=models.CharField(default='#1a365d', max_length=7),
        ),
        migrations.AddField(
            model_name='portal',
            name='facebook',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='portal',
            name='favicon',
            field=models.ImageField(blank=True, null=True, upload_to=plataforma.models.upload_portal_favicon),
        ),
        migrations.AddField(
            model_name='portal',
            name='imagem_compartilhamento',
            field=models.ImageField(
                blank=True,
                help_text='Imagem Open Graph / compartilhamento.',
                null=True,
                upload_to=plataforma.models.upload_portal_og,
            ),
        ),
        migrations.AddField(
            model_name='portal',
            name='instagram',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='portal',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to=plataforma.models.upload_portal_logo),
        ),
        migrations.AddField(
            model_name='portal',
            name='seo_description',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name='portal',
            name='seo_title',
            field=models.CharField(blank=True, max_length=70),
        ),
        migrations.AddField(
            model_name='portal',
            name='texto_rodape',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='portal',
            name='tiktok',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='portal',
            name='twitter',
            field=models.URLField(blank=True, verbose_name='X / Twitter'),
        ),
        migrations.AddField(
            model_name='portal',
            name='youtube',
            field=models.URLField(blank=True),
        ),
        migrations.RunPython(aplicar_identidade, reverter),
    ]
