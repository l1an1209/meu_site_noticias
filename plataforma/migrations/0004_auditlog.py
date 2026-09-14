from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('plataforma', '0003_corrigir_seo_portalbeta'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('acao', models.CharField(db_index=True, max_length=80)),
                ('objeto', models.CharField(blank=True, max_length=120)),
                ('objeto_id', models.CharField(blank=True, max_length=40)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('detalhes', models.JSONField(blank=True, default=dict)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('portal', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='auditoria',
                    to='plataforma.portal',
                )),
                ('usuario', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='auditoria',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Registro de auditoria',
                'verbose_name_plural': 'Auditoria',
                'ordering': ['-criado_em'],
            },
        ),
    ]
