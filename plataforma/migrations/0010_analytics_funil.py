import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0009_planos_nomes_precos_comerciais'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalyticsSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rotulo', models.CharField(db_index=True, max_length=8)),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('visto_em', models.DateTimeField(db_index=True)),
                ('path_primeiro', models.CharField(blank=True, max_length=200)),
                ('path_atual', models.CharField(blank=True, max_length=200)),
                ('referrer', models.CharField(blank=True, max_length=300)),
                ('utm_source', models.CharField(blank=True, max_length=80)),
                ('utm_medium', models.CharField(blank=True, max_length=80)),
                ('utm_campaign', models.CharField(blank=True, max_length=120)),
                ('utm_content', models.CharField(blank=True, max_length=120)),
                ('utm_term', models.CharField(blank=True, max_length=120)),
                ('fbclid', models.CharField(blank=True, max_length=200)),
                ('fbp', models.CharField(blank=True, max_length=80)),
                ('fbc', models.CharField(blank=True, max_length=200)),
                ('dispositivo', models.CharField(choices=[('unknown', 'Desconhecido'), ('mobile', 'Mobile'), ('tablet', 'Tablet'), ('desktop', 'Desktop')], default='unknown', max_length=16)),
                ('portal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='analytics_sessoes', to='plataforma.portal')),
            ],
            options={
                'verbose_name': 'Sessão de analytics',
                'verbose_name_plural': 'Sessões de analytics',
                'ordering': ['-visto_em'],
            },
        ),
        migrations.CreateModel(
            name='AnalyticsEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(db_index=True, max_length=40)),
                ('path', models.CharField(blank=True, max_length=200)),
                ('extra', models.JSONField(blank=True, default=dict)),
                ('ref_externo', models.CharField(blank=True, db_index=True, max_length=80)),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('portal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='analytics_eventos', to='plataforma.portal')),
                ('sessao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eventos', to='plataforma.analyticssession')),
            ],
            options={
                'verbose_name': 'Evento de analytics',
                'verbose_name_plural': 'Eventos de analytics',
                'ordering': ['criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='analyticssession',
            index=models.Index(fields=['visto_em'], name='plataforma__visto_e_an1_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticssession',
            index=models.Index(fields=['portal', 'visto_em'], name='plataforma__portal__an2_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticsevent',
            index=models.Index(fields=['tipo', 'criado_em'], name='plataforma__tipo_cr_an3_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticsevent',
            index=models.Index(fields=['sessao', 'criado_em'], name='plataforma__sessao__an4_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticsevent',
            index=models.Index(fields=['portal', 'tipo', 'criado_em'], name='plataforma__portal__an5_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticsevent',
            index=models.Index(fields=['tipo', 'ref_externo'], name='plataforma__tipo_re_an6_idx'),
        ),
    ]
