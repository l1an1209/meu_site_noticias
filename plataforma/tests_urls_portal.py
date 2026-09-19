"""URLs públicas e do painel do tenant (slug / host_previsto / custom_domain)."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from plataforma.models import Portal
from plataforma.resolvers import resolve_portal_from_host
from plataforma.services.acesso import enviar_acesso
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY
from plataforma.urls_portal import url_app_portal, url_publica_portal

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_BASE_DOMAIN='plataforma.com.br',
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class UrlsPortalClienteTests(MockResendMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = Portal.objects.create(
            nome='Portal Cliente',
            slug='cliente-demo',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )

    def test_slug_gera_url_publica_e_painel(self):
        self.assertEqual(self.portal.host_previsto, 'cliente-demo.plataforma.com.br')
        self.assertEqual(
            url_publica_portal(self.portal),
            'https://cliente-demo.plataforma.com.br/',
        )
        self.assertEqual(
            url_app_portal(self.portal),
            'https://cliente-demo.plataforma.com.br/app/',
        )
        self.assertNotIn('portal_id', url_app_portal(self.portal))
        self.assertNotIn('?', url_publica_portal(self.portal))
        self.assertNotIn('?', url_app_portal(self.portal))

    def test_custom_domain_tem_prioridade(self):
        self.portal.custom_domain = 'noticias.cidade.com.br'
        self.portal.save(update_fields=['custom_domain'])
        self.assertEqual(url_publica_portal(self.portal), 'https://noticias.cidade.com.br/')
        self.assertEqual(url_app_portal(self.portal), 'https://noticias.cidade.com.br/app/')
        self.assertEqual(
            resolve_portal_from_host('noticias.cidade.com.br').pk,
            self.portal.pk,
        )
        self.assertEqual(
            resolve_portal_from_host('cliente-demo.plataforma.com.br').pk,
            self.portal.pk,
        )

    def test_localhost_nao_e_tenant(self):
        self.assertIsNone(resolve_portal_from_host('localhost'))
        self.assertIsNone(resolve_portal_from_host('127.0.0.1'))
        self.assertIsNone(resolve_portal_from_host('localhost:8000'))
        self.assertIsNone(resolve_portal_from_host('127.0.0.1:8000'))
        self.assertEqual(
            resolve_portal_from_host('cliente-demo.plataforma.com.br').pk,
            self.portal.pk,
        )

    def test_email_onboarding_mostra_urls_sem_senha(self):
        usuario = User.objects.create_user('cliente-demo', 'cliente@demo.test', 'senha-temporaria-xyz')
        resultado = enviar_acesso(usuario, self.portal)
        self.assertTrue(resultado.ok)
        corpo = self.resend_payloads[-1]['text']
        self.assertIn('Seu portal foi criado com sucesso.', corpo)
        self.assertIn('Acessar meu site', corpo)
        self.assertIn('https://cliente-demo.plataforma.com.br/', corpo)
        self.assertIn('Administrar meu portal', corpo)
        self.assertIn('https://cliente-demo.plataforma.com.br/app/', corpo)
        self.assertIn('/senha/redefinir/', corpo)
        self.assertNotIn('senha-temporaria-xyz', corpo)
        self.assertNotIn('portal_id=', corpo)

    def test_master_abre_site_e_painel_em_nova_aba(self):
        master = User.objects.create_superuser('url-master', 'url-master@test.com', 'senha-forte-ops')
        self.client.force_login(master)
        host = {'HTTP_HOST': 'localhost'}
        detalhe = self.client.get(reverse('master_portal', args=[self.portal.pk]), **host)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, 'Abrir site')
        self.assertContains(detalhe, 'Abrir painel')
        self.assertContains(detalhe, 'https://cliente-demo.plataforma.com.br/')
        self.assertContains(detalhe, 'https://cliente-demo.plataforma.com.br/app/')
        self.assertContains(detalhe, 'target="_blank"')
        self.assertNotContains(detalhe, '/app/?portal_id=')

        lista = self.client.get(reverse('master_portais'), **host)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Abrir site')
        self.assertContains(lista, 'https://cliente-demo.plataforma.com.br/')
        self.assertNotContains(lista, '/app/?portal_id=')


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_BASE_DOMAIN='portalnoticias.com.br',
    TENANT_COMPAT_FALLBACK=False,
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class HostsPlataformaProducaoTests(TestCase):
    def test_dominio_principal_nao_e_tenant(self):
        Portal.objects.create(
            nome='Colisão de slug',
            slug='portalnoticias',
            cidade='Brasil',
            estado='BR',
            status=Portal.STATUS_ATIVO,
        )
        self.assertIsNone(resolve_portal_from_host('portalnoticias.com.br'))
        self.assertIsNone(resolve_portal_from_host('www.portalnoticias.com.br'))
        self.assertIsNone(resolve_portal_from_host('meu-site-noticias.onrender.com'))

    def test_subdominio_cliente_continua_tenant(self):
        portal = Portal.objects.create(
            nome='Portal Cliente',
            slug='cliente-novo',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
        )
        self.assertEqual(
            url_publica_portal(portal),
            'https://cliente-novo.portalnoticias.com.br/',
        )
        self.assertEqual(
            url_app_portal(portal),
            'https://cliente-novo.portalnoticias.com.br/app/',
        )
        self.assertEqual(
            resolve_portal_from_host('cliente-novo.portalnoticias.com.br').pk,
            portal.pk,
        )

    def test_home_do_apex_e_landing_saas(self):
        resp = self.client.get('/', HTTP_HOST='portalnoticias.com.br')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Tenha seu próprio portal profissional.')
        self.assertNotContains(resp, 'Notícias Ji-Paraná')

