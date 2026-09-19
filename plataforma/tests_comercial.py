"""Etapa 6: Kiwify, onboarding, assinatura e isolamento comercial."""
import hashlib
import hmac
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Noticia
from plataforma.models import Assinatura, Cliente, Membership, Plano, Portal, WebhookEvent
from plataforma.services.kiwify import assinatura_kiwify
from plataforma.slugs import gerar_slug_portal, slug_disponivel
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY

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
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class ComercialKiwifyTests(MockResendMixin, TestCase):
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
        self.assertEqual(resp.json().get('classe'), 'aprovado')
        self.assertEqual(Cliente.objects.filter(email='joao@campinas.test').count(), 1)
        self.assertEqual(Portal.objects.filter(cliente__email='joao@campinas.test').count(), 1)
        portal = Portal.objects.get(cliente__email='joao@campinas.test')
        self.assertEqual(portal.status, Portal.STATUS_ATIVO)
        self.assertTrue(portal.slug.startswith('setup-'))
        self.assertNotEqual(portal.slug, 'noticias-de-campinas')
        self.assertEqual(portal.nome, 'Portal em configuração')
        self.assertFalse(portal.setup_concluido)
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

    def test_assinatura_na_query_string_e_aceita(self):
        body = _payload_aprovado(
            order_id='ord-qs-1', email='qs@campinas.test', sub_id='sub-qs-1',
            product='Portal Query String',
        )
        sig = body.pop('signature')
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse('webhook_kiwify') + '?signature=' + sig,
                data=json.dumps(body),
                content_type='application/json',
                HTTP_HOST='localhost',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Cliente.objects.filter(email='qs@campinas.test').count(), 1)
        self.assertEqual(Portal.objects.filter(cliente__email='qs@campinas.test').count(), 1)

    def test_query_string_assinatura_errada_rejeita(self):
        body = _payload_aprovado(
            order_id='ord-qs-bad', email='badqs@campinas.test', sub_id='sub-qs-bad',
        )
        body.pop('signature', None)
        resp = self.client.post(
            reverse('webhook_kiwify') + '?signature=0000000000000000000000000000000000000000',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Cliente.objects.filter(email='badqs@campinas.test').count(), 0)

    def test_sem_assinatura_rejeita(self):
        body = _payload_aprovado(order_id='ord-nosig', email='nosig@campinas.test', sub_id='sub-nosig')
        body.pop('signature', None)
        resp = self._post(body)
        self.assertEqual(resp.status_code, 401)

    def test_hmac_do_corpo_bruto_na_query_e_aceito(self):
        body = _payload_aprovado(
            order_id='ord-body-1', email='bodyhmac@campinas.test', sub_id='sub-body-1',
            product='Portal HMAC Corpo',
        )
        body.pop('signature', None)
        bruto = json.dumps(body).encode('utf-8')
        sig = hmac.new(SECRET.encode('utf-8'), bruto, hashlib.sha1).hexdigest()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse('webhook_kiwify') + '?signature=' + sig,
                data=bruto,
                content_type='application/json',
                HTTP_HOST='localhost',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Cliente.objects.filter(email='bodyhmac@campinas.test').count(), 1)

    def test_sha1_order_id_concat_token_na_query_e_aceito(self):
        body = _payload_aprovado(
            order_id='ord-sha1-1', email='sha1c@campinas.test', sub_id='sub-sha1-1',
            product='Portal SHA1 Concat',
        )
        body.pop('signature', None)
        sig = hashlib.sha1(b'ord-sha1-1' + SECRET.encode('utf-8')).hexdigest()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse('webhook_kiwify') + '?signature=' + sig,
                data=json.dumps(body),
                content_type='application/json',
                HTTP_HOST='localhost',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(Cliente.objects.filter(email='sha1c@campinas.test').count(), 1)

    def test_md5_legado_e_rejeitado(self):
        body = _payload_aprovado(
            order_id='ord-md5-1', email='md5@campinas.test', sub_id='sub-md5-1',
        )
        body['signature'] = hashlib.md5(b'ord-md5-1' + SECRET.encode('utf-8')).hexdigest()
        resp = self._post(body)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Cliente.objects.filter(email='md5@campinas.test').count(), 0)

    def test_pagamento_pendente_altera_status(self):
        self._post(_payload_aprovado())
        late = _payload_aprovado(order_id='ord-002')
        late['webhook_event_type'] = 'pix_gerado'
        late['signature'] = assinatura_kiwify('ord-002', SECRET)
        resp = self._post(late)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('classe'), 'pendente')
        sub = Assinatura.objects.get(kiwify_subscription_id='sub-001')
        self.assertEqual(sub.status, Assinatura.STATUS_PENDENTE)
        self.assertEqual(Noticia.all_objects.filter(portal=sub.portal).count(), 0)

    def test_pix_created_e_pendente_nao_aprovado(self):
        self._post(_payload_aprovado())
        pix = _payload_aprovado(order_id='ord-pix-created')
        pix['webhook_event_type'] = 'pix_created'
        pix['order_status'] = 'waiting_payment'
        pix['signature'] = assinatura_kiwify('ord-pix-created', SECRET)
        resp = self._post(pix)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data.get('ok'))
        self.assertFalse(data.get('ignorado'))
        self.assertEqual(data.get('classe'), 'pendente')
        sub = Assinatura.objects.get(kiwify_subscription_id='sub-001')
        self.assertEqual(sub.status, Assinatura.STATUS_PENDENTE)
        self.assertEqual(Assinatura.objects.filter(kiwify_order_id='ord-001').count(), 1)

    def test_compra_aprovada_cria_assinatura(self):
        body = _payload_aprovado(
            order_id='ord-pt-ok', email='aprovapt@campinas.test', sub_id='sub-pt-ok',
            product='Portal Compra Aprovada',
        )
        body['webhook_event_type'] = 'compra_aprovada'
        body['signature'] = assinatura_kiwify('ord-pt-ok', SECRET)
        resp = self._post(body)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json().get('classe'), 'aprovado')
        self.assertEqual(Assinatura.objects.get(kiwify_order_id='ord-pt-ok').status, Assinatura.STATUS_ATIVA)

    def test_evento_desconhecido_retorna_200_ignorado(self):
        body = _payload_aprovado(
            order_id='ord-unk', email='unk@campinas.test', sub_id='sub-unk',
        )
        body['webhook_event_type'] = 'evento_que_nao_existe'
        body['signature'] = assinatura_kiwify('ord-unk', SECRET)
        resp = self._post(body)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data.get('ok'))
        self.assertTrue(data.get('ignorado'))
        self.assertEqual(Cliente.objects.filter(email='unk@campinas.test').count(), 0)
        evento = WebhookEvent.objects.get(id_externo='ord-unk')
        self.assertEqual(evento.status, WebhookEvent.STATUS_IGNORADO)

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
        portal.setup_concluido = True
        portal.save(update_fields=['setup_concluido'])
        self.client.force_login(user)
        self.client.defaults['HTTP_HOST'] = f'{portal.slug}.test'
        self.assertEqual(self.client.get(reverse('app_home')).status_code, 200)

    def test_cliente_a_nao_acessa_cliente_b(self):
        self._post(_payload_aprovado(email='a@t.test', order_id='oa', sub_id='sa', product='Portal Alfa Com'))
        self._post(_payload_aprovado(email='b@t.test', order_id='ob', sub_id='sb', product='Portal Beta Com'))
        pa = Portal.objects.get(cliente__email='a@t.test')
        pb = Portal.objects.get(cliente__email='b@t.test')
        pa.setup_concluido = True
        pa.save(update_fields=['setup_concluido'])
        pb.setup_concluido = True
        pb.save(update_fields=['setup_concluido'])
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
        html2_l = html2.lower()
        self.assertIn('sa3', html2_l)
        self.assertIn('sb3', html2_l)
        self.assertIn('setup-', html2_l)
        self.assertNotIn('alfa-tres', html2_l)

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
        self.assertContains(resp, 'Tenha seu próprio portal profissional.')
        self.assertContains(resp, 'sales-hero')
        self.assertNotContains(resp, 'Este portal está temporariamente fora do ar')
        self.assertTrue(Plano.objects.filter(codigo='basico', nome='Start', preco_mensal='29.90').exists())
        self.assertTrue(Plano.objects.filter(codigo='profissional', nome='Pro', preco_mensal='49.90').exists())
        self.assertTrue(Plano.objects.filter(codigo='premium', nome='Premium', preco_mensal='69.90').exists())
        self.assertContains(resp, 'Começar com o Start')
        self.assertContains(resp, 'Começar com o Pro</a>')
        self.assertContains(resp, 'Começar com o Premium')
        self.assertNotContains(resp, 'Começar com o Básico')
        self.assertNotContains(resp, 'Começar com o Profissional')
        self.assertNotContains(resp, 'R$ 59,90')
        self.assertNotContains(resp, 'R$ 79,90')
        self.assertNotContains(resp, 'R$ 99,90')
        self.assertContains(resp, 'Recomendado')
        html = resp.content.decode()
        self.assertIn(reverse('pagina_checkout_plano', args=['basico']), html)
        self.assertIn(reverse('pagina_checkout_plano', args=['profissional']), html)
        self.assertIn(reverse('pagina_checkout_plano', args=['premium']), html)
        self.assertNotIn(reverse('pagina_checkout_plano', args=['inicial']), html)
        self.assertNotIn('Inicial', html)

    def test_checkout_identifica_cada_plano_sem_confundir(self):
        urls = {
            'basico': 'https://pay.kiwify.com.br/ck-basico',
            'profissional': 'https://pay.kiwify.com.br/ck-pro',
            'premium': 'https://pay.kiwify.com.br/ck-premium',
        }
        nomes = {
            'basico': 'Start',
            'profissional': 'Pro',
            'premium': 'Premium',
        }
        precos = {
            'basico': '29,90',
            'profissional': '49,90',
            'premium': '69,90',
        }
        for codigo, url in urls.items():
            Plano.objects.filter(codigo=codigo).update(checkout_url=url)

        for codigo, nome in nomes.items():
            resp = self.client.get(
                reverse('pagina_checkout_plano', args=[codigo]),
                HTTP_HOST='localhost',
            )
            self.assertEqual(resp.status_code, 200, codigo)
            html = resp.content.decode()
            self.assertContains(resp, f'Começar com o {nome}</h1>')
            self.assertContains(resp, precos[codigo])
            self.assertIn(f'data-plano-codigo="{codigo}"', html)
            self.assertIn(f'data-checkout-plano="{codigo}"', html)
            self.assertIn(urls[codigo], html)
            self.assertIn(f'Pagar o {nome} na Kiwify', html)
            for outro, outro_url in urls.items():
                if outro == codigo:
                    continue
                self.assertNotIn(outro_url, html)
                self.assertNotIn(f'data-checkout-plano="{outro}"', html)
                self.assertNotIn(f'data-plano-codigo="{outro}"', html)
                self.assertNotContains(resp, f'Começar com o {nomes[outro]}</h1>')

        resp = self.client.get('/comece/inicial/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get('/comece/plano-inventado/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 404)

    def test_slug_reservado(self):
        self.assertFalse(slug_disponivel('admin'))
        self.assertFalse(slug_disponivel('www'))
        slug = gerar_slug_portal('Admin', 'pessoa@test.com')
        self.assertNotEqual(slug, 'admin')
        self.assertTrue(slug_disponivel(slug))

    def test_home_plataforma_e_landing_saas_e_tenant_continua_portal(self):
        resp = self.client.get('/', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('Tenha seu próprio portal profissional.', html)
        self.assertIn('COMEÇAR AGORA', html)
        self.assertIn(reverse('pagina_vendas'), html)
        self.assertIn('home-saas', html)
        self.assertIn('Começar com o Start', html)
        self.assertIn('Começar com o Pro</a>', html)
        self.assertIn('Começar com o Premium', html)
        self.assertNotIn('R$ 59,90', html)
        self.assertNotIn('R$ 79,90', html)
        self.assertNotIn('R$ 99,90', html)
        self.assertNotIn('Ji-Paraná', html)
        self.assertNotIn('mosaic-hero', html)
        comece = self.client.get(reverse('pagina_vendas'), HTTP_HOST='localhost')
        self.assertEqual(comece.status_code, 200)
        self.assertContains(comece, 'sales-hero')
        self.assertContains(comece, 'Tenha seu próprio portal profissional.')
        tenant = self.client.get('/', HTTP_HOST=f'{Portal.SLUG_LEGADO}.test')
        self.assertEqual(tenant.status_code, 200)
        self.assertNotContains(tenant, 'COMEÇAR AGORA')
        self.assertContains(tenant, Portal.objects.get(slug=Portal.SLUG_LEGADO).nome)
        fav = self.client.get('/favicon.ico', HTTP_HOST='localhost')
        self.assertEqual(fav.status_code, 302)
        self.assertIn('portalup-icon.svg', fav['Location'])


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class KiwifyIdentidadePortalTests(MockResendMixin, TestCase):
    def _post(self, payload):
        return self.client.post(
            reverse('webhook_kiwify'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='localhost',
        )

    def test_product_name_nao_define_slug_nem_nome(self):
        resp = self._post(_payload_aprovado(
            order_id='ord-id-1',
            email='id1@campinas.test',
            sub_id='sub-id-1',
            product='Plano Básico',
        ))
        self.assertEqual(resp.status_code, 200, resp.content)
        portal = Portal.objects.get(cliente__email='id1@campinas.test')
        self.assertNotEqual(portal.slug, 'plano-basico')
        self.assertTrue(portal.slug.startswith('setup-'))
        self.assertLessEqual(len(portal.slug), 50)
        self.assertNotEqual(portal.nome, 'Plano Básico')
        self.assertEqual(portal.nome, 'Portal em configuração')
        self.assertIs(portal.setup_concluido, False)
        self.assertEqual(portal.plano.codigo, 'basico')
        self.assertNotIn('campinas', portal.slug)
        self.assertNotIn('id1', portal.slug)

    def test_segundo_provisionamento_slug_unico(self):
        self._post(_payload_aprovado(
            order_id='ord-id-2a', email='id2a@campinas.test', sub_id='sub-id-2a',
            product='Plano Básico',
        ))
        self._post(_payload_aprovado(
            order_id='ord-id-2b', email='id2b@campinas.test', sub_id='sub-id-2b',
            product='Plano Profissional',
        ))
        p1 = Portal.objects.get(cliente__email='id2a@campinas.test')
        p2 = Portal.objects.get(cliente__email='id2b@campinas.test')
        self.assertTrue(p1.slug.startswith('setup-'))
        self.assertTrue(p2.slug.startswith('setup-'))
        self.assertNotEqual(p1.slug, p2.slug)
        self.assertNotEqual(p1.slug, 'plano-profissional')
        self.assertNotEqual(p2.slug, 'plano-profissional')
        self.assertIs(p1.setup_concluido, False)
        self.assertIs(p2.setup_concluido, False)

    def test_provisionamento_nao_altera_legado_plano_basico(self):
        legado = Portal.objects.filter(slug='plano-basico').first()
        if legado is None:
            legado = Portal.objects.create(
                nome='Notícias',
                slug='plano-basico',
                cidade='Campinas',
                estado='SP',
                setup_concluido=True,
            )
        slug_antes = legado.slug
        nome_antes = legado.nome
        setup_antes = legado.setup_concluido
        self._post(_payload_aprovado(
            order_id='ord-id-leg', email='idleg@campinas.test', sub_id='sub-id-leg',
            product='Plano Básico',
        ))
        legado.refresh_from_db()
        self.assertEqual(legado.slug, slug_antes)
        self.assertEqual(legado.nome, nome_antes)
        self.assertEqual(legado.setup_concluido, setup_antes)
        novo = Portal.objects.get(cliente__email='idleg@campinas.test')
        self.assertNotEqual(novo.pk, legado.pk)
        self.assertTrue(novo.slug.startswith('setup-'))
        self.assertEqual(Portal.objects.filter(slug='plano-basico').count(), 1)
