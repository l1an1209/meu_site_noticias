# Generated manually for portal Jiparaná

from django.db import migrations, models


def criar_slots_anuncio(apps, schema_editor):
    Anuncio = apps.get_model('noticias', 'Anuncio')
    slots = [
        ('top', 'Banner topo'),
        ('sidebar', 'Barra lateral'),
        ('article', 'Dentro da notícia'),
    ]
    for slot, nome in slots:
        Anuncio.objects.get_or_create(
            slot=slot,
            defaults={'titulo_interno': nome, 'ativo': False},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('noticias', '0007_alter_noticia_options_noticia_autor_noticia_destaque_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribuicao',
            name='observacao_admin',
            field=models.TextField(blank=True, verbose_name='Sua observação (interna)'),
        ),
        migrations.AddField(
            model_name='contribuicao',
            name='telefone',
            field=models.CharField(blank=True, max_length=20, verbose_name='WhatsApp / telefone'),
        ),
        migrations.AlterField(
            model_name='contribuicao',
            name='status',
            field=models.CharField(
                choices=[
                    ('pendente', 'Aguardando sua análise'),
                    ('aprovado', 'Publicado no site'),
                    ('rejeitado', 'Não publicado'),
                ],
                db_index=True,
                default='pendente',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='Anuncio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot', models.CharField(
                    choices=[
                        ('top', 'Banner topo (abaixo do menu)'),
                        ('sidebar', 'Barra lateral'),
                        ('article', 'Dentro da notícia'),
                    ],
                    max_length=20,
                    unique=True,
                    verbose_name='Posição',
                )),
                ('titulo_interno', models.CharField(max_length=100, verbose_name='Nome do anunciante')),
                ('ativo', models.BooleanField(default=False, verbose_name='Exibir no site')),
                ('codigo_html', models.TextField(
                    blank=True,
                    help_text='Cole aqui o código do Google AdSense ou HTML do parceiro.',
                    verbose_name='Código HTML (AdSense)',
                )),
                ('imagem', models.ImageField(blank=True, null=True, upload_to='anuncios/')),
                ('link', models.URLField(blank=True, verbose_name='Link ao clicar na imagem')),
            ],
            options={
                'verbose_name': 'Anúncio',
                'verbose_name_plural': 'Anúncios (espaços reservados)',
            },
        ),
        migrations.RunPython(criar_slots_anuncio, migrations.RunPython.noop),
    ]
