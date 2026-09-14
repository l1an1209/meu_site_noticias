from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def seed_planos(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    specs = [
        {
            'codigo': 'basico',
            'nome': 'Básico',
            'preco_mensal': Decimal('59.90'),
            'descricao': 'Portal de notícias da sua cidade, com painel completo.',
            'recursos': 'Site com a identidade da cidade\nPainel para publicar notícias\nFotos e vídeos\n1 administrador\n1 GB de mídia',
            'max_storage_mb': 1024,
            'max_usuarios': 3,
            'ordem': 1,
        },
        {
            'codigo': 'profissional',
            'nome': 'Profissional',
            'preco_mensal': Decimal('79.90'),
            'descricao': 'Para redações que publicam todo dia.',
            'recursos': 'Tudo do Básico\nEquipe com editores e autores\nEnvios da comunidade\nSEO e aparência avançados\n5 GB de mídia',
            'max_storage_mb': 5120,
            'max_usuarios': 8,
            'ordem': 2,
        },
        {
            'codigo': 'premium',
            'nome': 'Premium',
            'preco_mensal': Decimal('99.90'),
            'descricao': 'Marca completa, mídia e publicidade no seu domínio futuro.',
            'recursos': 'Tudo do Profissional\nPublicidade no site\nMais usuários da equipe\nPrioridade no suporte\n15 GB de mídia',
            'max_storage_mb': 15360,
            'max_usuarios': 15,
            'ordem': 3,
        },
    ]
    for spec in specs:
        Plano.objects.update_or_create(codigo=spec['codigo'], defaults=spec)


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0004_auditlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='plano',
            name='checkout_url',
            field=models.URLField(blank=True, help_text='Link de checkout Kiwify deste plano.'),
        ),
        migrations.AddField(
            model_name='plano',
            name='descricao',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='plano',
            name='kiwify_plan_id',
            field=models.CharField(blank=True, db_index=True, help_text='Subscription.plan.id na Kiwify.', max_length=80),
        ),
        migrations.AddField(
            model_name='plano',
            name='kiwify_product_id',
            field=models.CharField(blank=True, db_index=True, help_text='Product.product_id na Kiwify.', max_length=80),
        ),
        migrations.AddField(
            model_name='plano',
            name='ordem',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='plano',
            name='preco_mensal',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Preço em reais. 0 = cortesia / legado.', max_digits=8),
        ),
        migrations.AddField(
            model_name='plano',
            name='recursos',
            field=models.TextField(blank=True, help_text='Um recurso por linha, exibido na página de venda.'),
        ),
        migrations.AlterModelOptions(
            name='plano',
            options={'ordering': ['ordem', 'preco_mensal', 'nome'], 'verbose_name': 'Plano', 'verbose_name_plural': 'Planos'},
        ),
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=160)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('telefone', models.CharField(blank=True, max_length=30)),
                ('status', models.CharField(choices=[('ativo', 'Ativo'), ('inativo', 'Inativo')], db_index=True, default='ativo', max_length=20)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'ordering': ['nome'],
            },
        ),
        migrations.AddField(
            model_name='portal',
            name='cliente',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='portais', to='plataforma.cliente'),
        ),
        migrations.CreateModel(
            name='Assinatura',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('aguardando_pagamento', 'Aguardando pagamento'), ('ativa', 'Ativa'), ('pagamento_pendente', 'Pagamento pendente'), ('atrasada', 'Atrasada'), ('cancelada', 'Cancelada'), ('bloqueada', 'Bloqueada')], db_index=True, default='aguardando_pagamento', max_length=32)),
                ('kiwify_subscription_id', models.CharField(blank=True, db_index=True, max_length=80)),
                ('kiwify_order_id', models.CharField(blank=True, db_index=True, max_length=80)),
                ('kiwify_transaction_id', models.CharField(blank=True, max_length=80)),
                ('iniciado_em', models.DateTimeField(blank=True, null=True)),
                ('proximo_vencimento', models.DateTimeField(blank=True, null=True)),
                ('cancelado_em', models.DateTimeField(blank=True, null=True)),
                ('bloqueado_em', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assinaturas', to='plataforma.cliente')),
                ('plano', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assinaturas', to='plataforma.plano')),
                ('portal', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='assinatura', to='plataforma.portal')),
            ],
            options={
                'verbose_name': 'Assinatura',
                'verbose_name_plural': 'Assinaturas',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddConstraint(
            model_name='assinatura',
            constraint=models.UniqueConstraint(condition=models.Q(('kiwify_order_id', ''), _negated=True), fields=('kiwify_order_id',), name='uniq_assinatura_kiwify_order'),
        ),
        migrations.AddConstraint(
            model_name='assinatura',
            constraint=models.UniqueConstraint(condition=models.Q(('kiwify_subscription_id', ''), _negated=True), fields=('kiwify_subscription_id',), name='uniq_assinatura_kiwify_sub'),
        ),
        migrations.CreateModel(
            name='WebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provedor', models.CharField(db_index=True, default='kiwify', max_length=40)),
                ('tipo', models.CharField(db_index=True, max_length=80)),
                ('id_externo', models.CharField(db_index=True, max_length=120)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('recebido', 'Recebido'), ('processado', 'Processado'), ('ignorado', 'Ignorado'), ('erro', 'Erro')], default='recebido', max_length=20)),
                ('processado', models.BooleanField(default=False)),
                ('erro', models.TextField(blank=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('processado_em', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Evento de webhook',
                'verbose_name_plural': 'Eventos de webhook',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddConstraint(
            model_name='webhookevent',
            constraint=models.UniqueConstraint(fields=('provedor', 'tipo', 'id_externo'), name='uniq_webhook_provedor_tipo_id'),
        ),
        migrations.RunPython(seed_planos, migrations.RunPython.noop),
    ]
