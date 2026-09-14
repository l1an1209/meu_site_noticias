"""Etapa 6: Kiwify, onboarding, assinatura e isolamento comercial."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Noticia
from plataforma.models import Assinatura, Cliente, Membership, Plano, Portal, WebhookEvent
from plataforma.services.kiwify import assinatura_kiwify
from plataforma.slugs import gerar_slug_portal, slug_disponivel

User = get_user_model()
SECRET = 'kiwify-token-teste'


def _payload_aprovado(order_id='ord-001', email='joao@campinas.test', sub_id='sub-001', product='Notícias de Campinas'):
    body = {
        'order_id': order_id,
        'order_ref': 'ABC123',
        'order_status': 'paid',
        'webhook_event_type': 'order_approved',
        'payment_merchant_id': 'txn-99',
        'Product': {'product_id': 'prod-campinas', 'product_name': product},
        'Customer': {
            'full_name': 'João da Silva',
            'email': email,
            'mobile': '19999999999',
            'city': 'Campinas',
            'state': 'SP',
        },
        'Subscription': {
            'id': sub_id,
            'start_date': '2026-09-14T12:00:00Z',
            'next_payment': '2026-10-14T12:00:00Z',
            'status': 'active',
            'plan': {'id': 'plan-pro', 'name': 'Profissional'},
        },
    }
    body['signature'] = assinatura_kiwify(order_id, SECRET)
    return body


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class ComercialKiwifyTests(TestCase):
    def _post(self, payload):
        return self.client.post(
            reverse('webhook_kiwify'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='localhost',
        )

    def test_pagamento_aprovado_cria_portal_usuario_e_assinatura(self):
        resp = self._post(_payload_aprovado())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Cliente.objects.filter(email='joao@campinas.test').count(), 1)
        self.assertEqual(Portal.objects.filter(cliente__email='joao@campinas.test').count(), 1)
        portal = Portal.objects.get(cliente__email='joao@campinas.test')
        self.assertEqual(portal.status, Portal.STATUS_ATIVO)
        self.assertTrue(portal.slug.startswith('noticias-de-campinas'))
        user = User.objects.get(email='joao@campinas.test')
        self.assertTrue(
            Membership.objects.filter(
                usuario=user, portal=portal, papel=Membership.PAPEL_ADMIN, ativo=True,
            ).exists()
        )
        sub = Assinatura.objects.get(portal=portal)
        self.assertEqual(sub.status, Assinatura.STATUS_ATIVA)
        self.assertEqual(sub.kiwify_order_id, 'ord-001')
        self.assertEqual(sub.kiwify_subscription_id, 'sub-001')
        self.assertEqual(sub.cliente.email, 'joao@campinas.test')
        self.assertEqual(sub.plano_id, portal.plano_id)

    def test_webhook_duplicado_nao_duplica(self):
        p = _payload_aprovado()
        self.assertEqual(self._post(p).status_code, 200)
        resp = self._post(p)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('duplicado'))
        self.assertEqual(Portal.objects.filter(cliente__email='joao@campinas.test').count(), 1)
        self.assertEqual(User.objects.filter(email='joao@campinas.test').count(), 1)
        self.assertEqual(Assinatura.objects.filter(kiwify_order_id='ord-001').count(), 1)
        self.assertEqual(WebhookEvent.objects.filter(id_externo='ord-001').count(), 1)

    def test_pagamento_pendente_altera_status(self):
        self._post(_payload_aprovado())
        late = _payload_aprovado(order_id='ord-002')
        late['webhook_event_type'] = 'pix_gerado'
        late['signature'] = assinatura_kiwify('ord-002', SECRET)
        self.assertEqual(self._post(late).status_code, 200)
        sub = Assinatura.objects.get(kiwify_subscription_id='sub-001')
        self.assertEqual(sub.status, Assinatura.STATUS_PENDENTE)
        self.assertEqual(Noticia.all_objects.filter(portal=sub.portal).count(), 0)

    def test_cancelamento_bloqueia_sem_apagar(self):
        self._post(_payload_aprovado())
        portal = Portal.objects.get(cliente__email='joao@campinas.test')
        Noticia.all_objects.create(
            portal=portal, titulo='Fica', conteudo='texto',
        )
        cancel = _payload_aprovado(order_id='ord-001')
        cancel['webhook_event_type'] = 'subscription_canceled'
        cancel['signature'] = assinatura_kiwify('ord-001', SECRET)
        self.assertEqual(self._post(cancel).status_code, 200)
        portal.refresh_from_db()
        self.assertEqual(portal.status, Portal.STATUS_BLOQUEADO)
        self.assertTrue(Noticia.all_objects.filter(portal=portal, titulo='Fica').exists())
        self.assertEqual(Assinatura.objects.get(portal=portal).status, Assinatura.STATUS_BLOQUEADA)

    def test_portal_bloqueado_nao_permite_admin_e_reativacao_recupera(self):
        self._post(_payload_aprovado())
        portal = Portal.objects.get(cliente__email='joao@campinas.test')
        user = User.objects.get(email='joao@campinas.test')
        cancel = _payload_aprovado()
        cancel['webhook_event_type'] = 'compra_reembolsada'
        self._post(cancel)
        self.client.force_login(user)
        self.client.defaults['HTTP_HOST'] = f'{portal.slug}.test'
        resp_app = self.client.get(reverse('app_home'))
        self.assertEqual(resp_app.status_code, 403)
        resp_pub = self.client.get('/')
        self.assertEqual(resp_pub.status_code, 403)
        self.assertIn('temporariamente', resp_pub.content.decode())
        master = User.objects.create_superuser('m6', 'm6@test.com', 'senha-forte-m6')
        self.client.force_login(master)
        resp = self.client.post(
            reverse('master_portal_acao', args=[portal.pk]),
            {'acao': 'reativar'},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 302)
        portal.refresh_from_db()
        self.assertEqual(portal.status, Portal.STATUS_ATIVO)
        self.client.force_login(user)
        self.client.defaults['HTTP_HOST'] = f'{portal.slug}.test'
        self.assertEqual(self.client.get(reverse('app_home')).status_code, 200)

    def test_cliente_a_nao_acessa_cliente_b(self):
        self._post(_payload_aprovado(email='a@t.test', order_id='oa', sub_id='sa', product='Portal Alfa Com'))
        self._post(_payload_aprovado(email='b@t.test', order_id='ob', sub_id='sb', product='Portal Beta Com'))
        pa = Portal.objects.get(cliente__email='a@t.test')
        pb = Portal.objects.get(cliente__email='b@t.test')
        ua = User.objects.get(email='a@t.test')
        self.client.force_login(ua)
        self.client.defaults['HTTP_HOST'] = f'{pb.slug}.test'
        self.assertEqual(self.client.get(reverse('app_home')).status_code, 403)
        self.assertEqual(self.client.get(reverse('app_assinatura')).status_code, 403)
        self.client.defaults['HTTP_HOST'] = f'{pa.slug}.test'
        html = self.client.get(reverse('app_assinatura')).content.decode()
        self.assertIn('a@t.test', html)
        self.assertNotIn('b@t.test', html)

    def test_cliente_nao_altera_assinatura_alheia(self):
        self._post(_payload_aprovado(email='a@t.test', order_id='oa2', sub_id='sa2', product='Alfa Dois'))
        self._post(_payload_aprovado(email='b@t.test', order_id='ob2', sub_id='sb2', product='Beta Dois'))
        pb = Portal.objects.get(cliente__email='b@t.test')
        ua = User.objects.get(email='a@t.test')
        self.client.force_login(ua)
        resp = self.client.post(
            reverse('master_portal_acao', args=[pb.pk]),
            {'acao': 'bloquear'},
            HTTP_HOST=f'{pb.slug}.test',
        )
        self.assertEqual(resp.status_code, 403)
        pb.refresh_from_db()
        self.assertEqual(pb.status, Portal.STATUS_ATIVO)

    def test_master_visualiza_todos(self):
        self._post(_payload_aprovado(email='a@t.test', order_id='oa3', sub_id='sa3', product='Alfa Tres'))
        self._post(_payload_aprovado(email='b@t.test', order_id='ob3', sub_id='sb3', product='Beta Tres'))
        master = User.objects.create_superuser('m7', 'm7@test.com', 'senha-forte-m7')
        self.client.force_login(master)
        html = self.client.get(reverse('master_clientes'), HTTP_HOST='localhost').content.decode()
        self.assertIn('a@t.test', html)
        self.assertIn('b@t.test', html)
        html2 = self.client.get(reverse('master_assinaturas'), HTTP_HOST='localhost').content.decode()
        self.assertIn('alfa-tres', html2.lower() + html2)

    def test_slug_duplicado_e_tratado(self):
        self._post(_payload_aprovado(email='um@t.test', order_id='s1', sub_id='u1', product='Cidade Igual'))
        self._post(_payload_aprovado(email='dois@t.test', order_id='s2', sub_id='u2', product='Cidade Igual'))
        slugs = list(
            Portal.objects.filter(cliente__email__in=['um@t.test', 'dois@t.test']).values_list('slug', flat=True)
        )
        self.assertEqual(len(slugs), 2)
        self.assertEqual(len(set(slugs)), 2)

    def test_webhook_invalido_e_rejeitado(self):
        p = _payload_aprovado()
        p['signature'] = 'invalida'
        resp = self._post(p)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(Cliente.objects.filter(email='joao@campinas.test').exists())

    def test_assinatura_e_plano_do_portal_certo(self):
        self._post(_payload_aprovado(email='x@t.test', order_id='ox', sub_id='sx', product='Portal X'))
        self._post(_payload_aprovado(email='y@t.test', order_id='oy', sub_id='sy', product='Portal Y'))
        px = Portal.objects.get(cliente__email='x@t.test')
        py = Portal.objects.get(cliente__email='y@t.test')
        ax = Assinatura.objects.get(portal=px)
        ay = Assinatura.objects.get(portal=py)
        self.assertEqual(ax.cliente.email, 'x@t.test')
        self.assertEqual(ay.cliente.email, 'y@t.test')
        self.assertEqual(ax.portal_id, px.pk)
        self.assertEqual(ay.portal_id, py.pk)
        self.assertEqual(ax.plano_id, px.plano_id)
        self.assertNotEqual(ax.pk, ay.pk)

    def test_pagina_vendas_e_master_planos(self):
        resp = self.client.get(reverse('pagina_vendas'), HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'R$')
        self.assertTrue(Plano.objects.filter(codigo='basico', preco_mensal='59.90').exists())

    def test_slug_reservado(self):
        self.assertFalse(slug_disponivel('admin'))
        self.assertFalse(slug_disponivel('www'))
        slug = gerar_slug_portal('Admin', 'pessoa@test.com')
        self.assertNotEqual(slug, 'admin')
        self.assertTrue(slug_disponivel(slug))
