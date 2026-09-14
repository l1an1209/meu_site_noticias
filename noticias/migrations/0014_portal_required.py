import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('noticias', '0013_seed_default_portal'),
        ('plataforma', '0001_portal_fk'),
    ]

    operations = [
        migrations.AlterField(
            model_name='anuncio',
            name='portal',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='anuncios',
                to='plataforma.portal',
            ),
        ),
        migrations.AlterField(
            model_name='categoria',
            name='portal',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='categorias',
                to='plataforma.portal',
            ),
        ),
        migrations.AlterField(
            model_name='contribuicao',
            name='portal',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='contribuicoes',
                to='plataforma.portal',
            ),
        ),
        migrations.AlterField(
            model_name='noticia',
            name='portal',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='noticias',
                to='plataforma.portal',
            ),
        ),
    ]
