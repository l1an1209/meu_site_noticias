from django.conf import settings
from django.db import migrations


SLUG_LEGADO = 'noticiasjiparana'


def seed_and_backfill(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    Portal = apps.get_model('plataforma', 'Portal')
    Membership = apps.get_model('plataforma', 'Membership')
    User = apps.get_model('auth', 'User')
    Categoria = apps.get_model('noticias', 'Categoria')
    Noticia = apps.get_model('noticias', 'Noticia')
    Contribuicao = apps.get_model('noticias', 'Contribuicao')
    Anuncio = apps.get_model('noticias', 'Anuncio')

    plano, _ = Plano.objects.get_or_create(
        codigo='inicial',
        defaults={
            'nome': 'Inicial',
            'max_storage_mb': 1024,
            'max_usuarios': 5,
        },
    )
    descricao = getattr(settings, 'SITE_DESCRIPTION', '') or ''
    portal, created = Portal.objects.get_or_create(
        slug=SLUG_LEGADO,
        defaults={
            'nome': getattr(settings, 'SITE_NAME', 'Notícias Ji-Paraná'),
            'cidade': getattr(settings, 'SITE_CITY', 'Ji-Paraná'),
            'estado': getattr(settings, 'SITE_STATE', 'RO'),
            'regiao': getattr(settings, 'SITE_REGION', ''),
            'slogan': getattr(settings, 'SITE_SLOGAN', ''),
            'tagline': getattr(settings, 'SITE_TAGLINE', ''),
            'descricao': descricao,
            'email': getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '',
            'latitude': getattr(settings, 'SITE_LAT', None),
            'longitude': getattr(settings, 'SITE_LON', None),
            'plano_id': plano.pk,
            'status': 'ativo',
            'pagamento_status': 'cortesia',
            'cliente_nome': '',
        },
    )
    if not created and portal.plano_id is None:
        portal.plano_id = plano.pk
        portal.save(update_fields=['plano_id'])

    for model in (Categoria, Noticia, Contribuicao, Anuncio):
        model.objects.filter(portal_id__isnull=True).update(portal_id=portal.pk)

    for user in User.objects.filter(is_staff=True, is_active=True):
        Membership.objects.get_or_create(
            usuario_id=user.pk,
            portal_id=portal.pk,
            defaults={'papel': 'admin', 'ativo': True},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('noticias', '0012_portal_fk'),
        ('plataforma', '0001_portal_fk'),
    ]

    operations = [
        migrations.RunPython(seed_and_backfill, noop_reverse),
    ]
