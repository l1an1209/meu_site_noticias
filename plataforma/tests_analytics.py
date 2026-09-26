from datetime import timedelta
import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from plataforma.models import AnalyticsEvent, AnalyticsSession, Plano, Portal
from plataforma.services.analytics import montar_dashboard
from plataforma.services.kiwify import assinatura_kiwify
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY

User = get_user_model()
SECRET = 'kiwify-token-teste'


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class AnalyticsFunilTests(MockResendMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.master = User.objects.create_superuser('an_master', 'anmaster@test.com', 'senha-forte-an')
        self.comum = User.objects.create_user('an_user', 'anuser@test.com', 'senha-forte-an')
        self.host = {'HTTP_HOST': 'localhost'}

    def _login_master(self):
        self.client.force_login(self.master)
        return self.host

    def test_page_view_cria_sessao_e_evento(self):
        resp = self.client.get('/', **self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AnalyticsSession.objects.count(), 1)
        self.assertTrue(AnalyticsEvent.objects.filter(tipo='view_home').exists())
        self.assertIn('pup_aid', resp.cookies)

    def test_planos_e_checkout_classificam_eventos(self):
        self.client.get('/', **self.host)
        self.client.get(reverse('pagina_vendas'), **self.host)
        self.client.get(reverse('pagina_checkout_plano', args=['basico']), **self.host)
        tipos = set(AnalyticsEvent.objects.values_list('tipo', flat=True))
        self.assertIn('view_home', tipos)
        self.assertIn('view_plans', tipos)
        self.assertIn('initiate_checkout', tipos)

    def test_collect_click_e_deduplica(self):
        self.client.get('/', **self.host)
        url = reverse('analytics_collect')
        payload = {'tipo': 'click_plan', 'path': '/comece/basico/', 'plano': 'basico', 'eid': 'e-1'}
        r1 = self.client.post(url, data=json.dumps(payload), content_type='application/json', **self.host)
        r2 = self.client.post(url, data=json.dumps(payload), content_type='application/json', **self.host)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(AnalyticsEvent.objects.filter(tipo='click_plan').count(), 1)

    def test_jornada_e_funil(self):
        self.client.get('/', **self.host)
        self.client.get(reverse('pagina_vendas'), **self.host)
        self.client.post(
            reverse('analytics_collect'),
            data=json.dumps({'tipo': 'click_subscribe', 'path': '/comece/'}),
            content_type='application/json',
            **self.host,
        )
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertGreaterEqual(dados['visitantes'], 1)
        self.assertGreaterEqual(dados['view_plans'], 1)
        self.assertGreaterEqual(dados['clicks'], 1)
        sessao = AnalyticsSession.objects.get()
        self.assertGreaterEqual(sessao.eventos.count(), 2)

    def test_master_somente_superuser(self):
        url = reverse('master_analytics')
        self.assertEqual(self.client.get(url, **self.host).status_code, 302)
        self.client.force_login(self.comum)
        self.assertEqual(self.client.get(url, **self.host).status_code, 403)
        self.assertEqual(self.client.get(reverse('master_analytics_agora'), **self.host).status_code, 403)
        self._login_master()
        resp = self.client.get(url, **self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Analytics comercial')
        self.assertContains(resp, 'Visitantes agora')
        live = self.client.get(reverse('master_analytics_agora'), **self.host)
        self.assertEqual(live.status_code, 200)
        self.assertTrue(live.json().get('ok'))

    def test_collect_tenant_nao_grava(self):
        legado = Portal.objects.filter(slug='noticiasjiparana').first()
        if legado is None:
            plano = Plano.objects.filter(codigo='inicial').first()
            legado = Portal.objects.create(
                nome='Legado', slug='noticiasjiparana', cidade='Ji-Paraná', estado='RO', plano=plano,
            )
        antes = AnalyticsEvent.objects.count()
        resp = self.client.post(
            reverse('analytics_collect'),
            data=json.dumps({'tipo': 'page_view', 'path': '/'}),
            content_type='application/json',
            HTTP_HOST=f'{legado.slug}.test',
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(AnalyticsEvent.objects.count(), antes)

    def test_isolamento_portal_no_filtro(self):
        p1 = Portal.objects.create(nome='A', slug='portal-a-an', cidade='X', estado='RO')
        p2 = Portal.objects.create(nome='B', slug='portal-b-an', cidade='Y', estado='RO')
        self.client.get('/', **self.host)
        s = AnalyticsSession.objects.get()
        AnalyticsEvent.objects.create(sessao=s, portal=p1, tipo='purchase', path='/comece/', extra={'valor': '29.90'})
        AnalyticsEvent.objects.create(sessao=s, portal=p2, tipo='purchase', path='/comece/', extra={'valor': '49.90'})
        d1 = montar_dashboard({'periodo': 'hoje', 'portal': str(p1.pk)})
        d2 = montar_dashboard({'periodo': 'hoje', 'portal': str(p2.pk)})
        self.assertEqual(d1['compras'], 1)
        self.assertEqual(d2['compras'], 1)

    def test_compra_kiwify_gera_purchase(self):
        body = {
            'order_id': 'ord-an-1',
            'order_status': 'paid',
            'webhook_event_type': 'order_approved',
            'Product': {'product_id': 'prod-an', 'product_name': 'Portal'},
            'Customer': {
                'full_name': 'Ana', 'email': 'ana-an@test.com',
                'mobile': '11999999999', 'city': 'Campinas', 'state': 'SP',
            },
            'Subscription': {
                'id': 'sub-an-1', 'start_date': now().isoformat(),
                'next_payment': now().isoformat(), 'status': 'active',
                'plan': {'id': 'plan-x', 'name': 'Start'},
            },
            'signature': assinatura_kiwify('ord-an-1', SECRET),
        }
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse('webhook_kiwify'),
                data=json.dumps(body),
                content_type='application/json',
                **self.host,
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(AnalyticsEvent.objects.filter(tipo='purchase', ref_externo='ord-an-1').exists())
        self.assertEqual(AnalyticsEvent.objects.filter(tipo='purchase', ref_externo='ord-an-1').count(), 1)
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertEqual(dados['compras'], 1)
        self.assertEqual(dados['compras_orfas'], 1)

    def test_meta_pixel_continua_na_home(self):
        resp = self.client.get('/', **self.host)
        html = resp.content.decode()
        self.assertIn('fbevents.js', html)
        self.assertIn('1628173745564370', html)
        self.assertIn('saas-analytics.js', html)

    def test_sidebar_cliente_nao_tem_analytics(self):
        self.client.force_login(self.comum)
        # painel do cliente exige portal; só conferimos que a URL master continua 403
        self.assertEqual(self.client.get(reverse('master_analytics'), **self.host).status_code, 403)

    def test_filtros_periodo(self):
        self.client.get('/', **self.host)
        self._login_master()
        for periodo in ('hoje', 'ontem', '7d', '30d'):
            resp = self.client.get(reverse('master_analytics') + f'?periodo={periodo}', **self.host)
            self.assertEqual(resp.status_code, 200, periodo)

    def test_jornada_master(self):
        self.client.get('/', **self.host)
        sessao = AnalyticsSession.objects.get()
        self.client.force_login(self.comum)
        self.assertEqual(
            self.client.get(reverse('master_analytics_sessao', args=[sessao.id]), **self.host).status_code,
            403,
        )
        self._login_master()
        resp = self.client.get(reverse('master_analytics_sessao', args=[sessao.id]), **self.host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, sessao.rotulo)
        self.assertContains(resp, 'view_home')

    def test_script_nao_duplica_a_mesma_abertura(self):
        self.client.get('/', **self.host)
        self.client.post(
            reverse('analytics_collect'),
            data=json.dumps({'tipo': 'page_view', 'path': '/'}),
            content_type='application/json',
            **self.host,
        )
        self.assertEqual(AnalyticsEvent.objects.filter(tipo='view_home').count(), 1)

    def test_segunda_visita_real_conta_de_novo(self):
        self.client.get('/', **self.host)
        evento = AnalyticsEvent.objects.get(tipo='view_home')
        evento.criado_em = now() - timedelta(minutes=10)
        evento.save(update_fields=['criado_em'])
        self.client.get('/', **self.host)
        self.assertEqual(AnalyticsEvent.objects.filter(tipo='view_home').count(), 2)

    def test_entrada_direta_fica_fora_do_funil_pago(self):
        self.client.get(reverse('pagina_checkout_plano', args=['basico']), **self.host)
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertEqual(dados['checkouts'], 1)
        self.assertEqual(dados['entrada_direta'], 1)
        checkout = next(etapa for etapa in dados['funil_pago'] if etapa['tipo'] == 'initiate_checkout')
        self.assertEqual(checkout['quantidade'], 0)
        self.assertEqual(dados['funil_pago'][0]['quantidade'], 0)

    def test_cadastro_de_leitor_nao_entra_no_funil_de_portal(self):
        self.client.get(reverse('cadastro'), **self.host)
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertGreaterEqual(dados['cadastros'], 1)
        tipos = {
            etapa['tipo']
            for bloco in (dados['funil_gratis'], dados['funil_pago'], dados['funil_comparacao'])
            for etapa in bloco
        }
        self.assertNotIn('registration_start', tipos)
        self.assertEqual(dados['funil_gratis'][0]['quantidade'], 0)
        self.assertEqual(dados['funil_pago'][0]['quantidade'], 0)

    def test_portal_gratis_criado_fica_na_sessao(self):
        from django.test import RequestFactory

        from plataforma.services.onboarding import provisionar_portal_gratuito

        self.client.get('/', **self.host)
        self.client.post(
            reverse('analytics_collect'),
            data=json.dumps({'tipo': 'click_subscribe', 'path': '/app/comecar/'}),
            content_type='application/json',
            **self.host,
        )
        sessao = AnalyticsSession.objects.get()
        pedido = RequestFactory().post('/app/comecar/', HTTP_HOST='localhost')
        pedido.COOKIES['pup_aid'] = str(sessao.id)
        provisionar_portal_gratuito(
            nome='Portal Analytics',
            email='ana.analytics@test.com',
            slug='portal-analytics-an',
            cidade='Campinas',
            estado='SP',
            senha='Senha-forte-portal-1',
            request=pedido,
        )
        self.assertTrue(AnalyticsEvent.objects.filter(tipo='portal_created', sessao=sessao).exists())
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertEqual(dados['portais_gratis'], 1)
        self.assertEqual(dados['portais_sem_clique'], 0)
        self.assertEqual(dados['funil_gratis'][0]['quantidade'], 1)
        self.assertEqual(dados['funil_gratis'][1]['quantidade'], 1)

    def test_compra_orfa_fica_fora_do_funil_pago(self):
        sessao = AnalyticsSession.objects.create(
            id=uuid.uuid4(),
            rotulo='Z99',
            visto_em=now(),
            path_primeiro='/comece/',
            path_atual='/comece/',
        )
        AnalyticsEvent.objects.create(
            sessao=sessao,
            tipo='purchase',
            path='/comece/',
            extra={'valor': '29.90'},
            ref_externo='ord-orfa-an',
        )
        dados = montar_dashboard({'periodo': 'hoje'})
        self.assertEqual(dados['compras'], 1)
        self.assertEqual(dados['compras_orfas'], 1)
        self.assertTrue(all(etapa['tipo'] != 'purchase' for etapa in dados['funil_pago']))
