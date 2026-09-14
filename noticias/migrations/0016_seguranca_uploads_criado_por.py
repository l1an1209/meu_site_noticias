from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import noticias.image_utils


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('noticias', '0015_alter_categoria_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='noticia',
            name='criado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='noticias_criadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='noticia',
            name='imagem',
            field=models.ImageField(
                blank=True,
                help_text='Foto principal (capa) da notícia.',
                null=True,
                upload_to=noticias.image_utils.upload_path_noticia,
            ),
        ),
        migrations.AlterField(
            model_name='noticia',
            name='video',
            field=models.FileField(
                blank=True,
                help_text='Vídeo da notícia (MP4, WebM).',
                null=True,
                upload_to=noticias.image_utils.upload_path_video_noticia,
            ),
        ),
        migrations.AlterField(
            model_name='contribuicao',
            name='video',
            field=models.FileField(
                blank=True,
                help_text='MP4 ou WebM, até 50 MB.',
                null=True,
                upload_to=noticias.image_utils.upload_path_video_contrib,
                verbose_name='Vídeo (opcional)',
            ),
        ),
        migrations.AlterField(
            model_name='anuncio',
            name='imagem',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=noticias.image_utils.upload_path_anuncio,
            ),
        ),
    ]
