from decimal import Decimal

from django.db import migrations


NOVOS_DADOS = {
    'basico': {'nome': 'Start', 'preco_mensal': Decimal('29.90')},
    'profissional': {'nome': 'Pro', 'preco_mensal': Decimal('49.90')},
    'premium': {'nome': 'Premium', 'preco_mensal': Decimal('69.90')},
}


def atualizar_nomes_e_precos(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    for codigo, dados in NOVOS_DADOS.items():
        Plano.objects.filter(codigo=codigo).update(
            nome=dados['nome'],
            preco_mensal=dados['preco_mensal'],
        )


def revert_nomes_e_precos(apps, schema_editor):
    Plano = apps.get_model('plataforma', 'Plano')
    antigos = {
        'basico': {'nome': 'Básico', 'preco_mensal': Decimal('59.90')},
        'profissional': {'nome': 'Profissional', 'preco_mensal': Decimal('79.90')},
        'premium': {'nome': 'Premium', 'preco_mensal': Decimal('99.90')},
    }
    for codigo, dados in antigos.items():
        Plano.objects.filter(codigo=codigo).update(
            nome=dados['nome'],
            preco_mensal=dados['preco_mensal'],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0008_alter_portal_setup_concluido'),
    ]

    operations = [
        migrations.RunPython(atualizar_nomes_e_precos, revert_nomes_e_precos),
    ]
