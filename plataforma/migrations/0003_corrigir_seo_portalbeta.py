from django.db import migrations


def corrigir_seo_beta(apps, schema_editor):
    Portal = apps.get_model('plataforma', 'Portal')
    Portal.objects.filter(slug='portalbeta').update(
        seo_description='SEO exclusivo do Portal Beta para Campinas e a plataforma.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0002_identidade_portal'),
    ]

    operations = [
        migrations.RunPython(corrigir_seo_beta, migrations.RunPython.noop),
    ]
