from decimal import Decimal

from django.db import migrations, models


RECURSOS_GRATUITO = (
    'Criação do portal\n'
    'Endereço no subdomínio da plataforma\n'
    'Identidade, logo e categorias\n'
    'Publicação de notícias, fotos e vídeos\n'
    'Páginas públicas e painel administrativo\n'
    'Pode exibir publicidade do PortalUP'
)


def criar_plano_gratuito(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    Plano.objects.get_or_create(
        codigo='gratuito',
        defaults={
            'nome': 'Gratuito',
            'descricao': (
                'Crie seu portal e publique suas notícias sem mensalidade. '
                'Pode conter publicidade do PortalUP.'
            ),
            'recursos': RECURSOS_GRATUITO,
            'preco_mensal': Decimal('0'),
            'max_storage_mb': 1024,
            'max_usuarios': 3,
            'ordem': 0,
            'ativo': True,
        },
    )
    Config = apps.get_model('plataforma', 'ConfiguracaoMonetizacao')
    Config.objects.get_or_create(
        pk=1,
        defaults={
            'ativa': False,
            'provedor': 'adsense',
            'posicoes': ['top', 'article'],
            'publicidade_gratuito': True,
            'publicidade_pago': False,
        },
    )


def remover_plano_gratuito(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    Plano.objects.filter(codigo='gratuito', preco_mensal=0).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0011_conversa_ajuda'),
    ]

    operations = [
        migrations.AddField(
            model_name='assinatura',
            name='origem',
            field=models.CharField(
                choices=[('kiwify', 'Kiwify'), ('gratuito', 'Gratuito')],
                db_index=True,
                default='kiwify',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='portal',
            name='publicidade_modo',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Seguir a política do plano'),
                    ('ativa', 'Exibir publicidade'),
                    ('inativa', 'Não exibir publicidade'),
                ],
                default='',
                help_text='Vazio segue a política global do plano. O Master pode ligar ou desligar neste portal.',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='portal',
            name='pagamento_status',
            field=models.CharField(
                choices=[
                    ('cortesia', 'Cortesia / legado'),
                    ('gratuito', 'Gratuito'),
                    ('pago', 'Pago'),
                    ('pendente', 'Pendente'),
                    ('atrasado', 'Atrasado'),
                ],
                default='cortesia',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='ConfiguracaoMonetizacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ativa', models.BooleanField(default=False)),
                ('provedor', models.CharField(
                    choices=[('adsense', 'AdSense'), ('outro', 'Outro'), ('propria', 'Própria')],
                    default='adsense',
                    max_length=20,
                )),
                ('publisher_id', models.CharField(
                    blank=True, help_text='Ex.: ca-pub-123. Usado no script único do AdSense.', max_length=40,
                )),
                ('codigo_script', models.TextField(
                    blank=True,
                    help_text='Script ou HTML do provedor. Carregado uma vez por página pública.',
                )),
                ('posicoes', models.JSONField(
                    blank=True,
                    default=list,
                    help_text='Posições permitidas: top, sidebar, article, feed, mobile.',
                )),
                ('publicidade_gratuito', models.BooleanField(
                    default=True,
                    help_text='Portais de plano gratuito herdam esta política.',
                )),
                ('publicidade_pago', models.BooleanField(
                    default=False,
                    help_text='Portais de plano pago herdam esta política.',
                )),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuração de monetização',
                'verbose_name_plural': 'Configuração de monetização',
            },
        ),
        migrations.RunPython(criar_plano_gratuito, remover_plano_gratuito),
    ]
