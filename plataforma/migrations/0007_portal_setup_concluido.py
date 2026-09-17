from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0006_emaillog_webhook_tentativas'),
    ]

    operations = [
        # 1) Default True para preencher TODOS os registros já existentes
        #    (noticiasjiparana, portalbeta, plano-basico, etc.).
        migrations.AddField(
            model_name='portal',
            name='setup_concluido',
            field=models.BooleanField(default=True),
        ),
        # 2) Default False daqui em diante (alinha ao model; não altera linhas já gravadas).
        migrations.AlterField(
            model_name='portal',
            name='setup_concluido',
            field=models.BooleanField(default=False),
        ),
    ]
