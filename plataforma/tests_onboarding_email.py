"""Fase 5: e-mail de acesso no onboarding incompleto."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from plataforma.models import Portal
from plataforma.services.acesso import enviar_acesso
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=['*'],
    SITE_URL='',
    TENANT_BASE_DOMAIN='portalnoticias.com.br',
    TENANT_COMPAT_FALLBACK=False,
    DEBUG=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class EmailOnboardingIncompletoTests(MockResendMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = Portal.objects.create(
            nome='Portal em configuração',
            slug='setup-87be50aa',
            cidade='Campinas',
            estado='SP',
            status=Portal.STATUS_ATIVO,
            setup_concluido=False,
        )
        self.usuario = User.objects.create_user(
            'onb_mail', 'onb-mail@test.com', 'senha-temporaria-xyz',
        )

    def _enviar(self):
        resultado = enviar_acesso(self.usuario, self.portal)
        self.assertTrue(resultado.ok)
        payload = self.resend_payloads[-1]
        return payload['subject'], payload['text']

    def test_mensagem_configuracao_inicial(self):
        assunto, corpo = self._enviar()
        self.assertEqual(assunto, 'Seu acesso à plataforma foi criado')
        self.assertIn('Pagamento confirmado', corpo)
        self.assertIn('configuração inicial', corpo.lower())

    def test_nao_expoe_slug_provisorio_como_url_principal(self):
        _, corpo = self._enviar()
        self.assertNotIn('https://setup-87be50aa.portalnoticias.com.br/', corpo)
        self.assertNotIn('https://setup-87be50aa.portalnoticias.com.br/app/', corpo)
        self.assertNotIn('setup-87be50aa.portalnoticias.com.br', corpo)
        self.assertNotIn('setup-87be50aa', corpo)

    def test_orienta_nome_e_subdominio(self):
        _, corpo = self._enviar()
        corpo_l = corpo.lower()
        self.assertIn('nome do seu portal', corpo_l)
        self.assertTrue('subdomínio' in corpo_l or 'subdominio' in corpo_l or 'endereço' in corpo_l)

    def test_link_entrada_plataforma_nao_usa_slug(self):
        _, corpo = self._enviar()
        entrar = f"https://portalnoticias.com.br{reverse('entrar')}"
        self.assertIn(entrar, corpo)
        self.assertNotIn('setup-87be50aa', corpo)

    def test_fluxo_senha_preservado(self):
        _, corpo = self._enviar()
        self.assertIn('/senha/redefinir/', corpo)
        self.assertIn('https://portalnoticias.com.br/senha/redefinir/', corpo)
        self.assertNotIn('senha-temporaria-xyz', corpo)


@override_settings(
    ALLOWED_HOSTS=['*'],
    SITE_URL='',
    TENANT_BASE_DOMAIN='portalnoticias.com.br',
    TENANT_COMPAT_FALLBACK=False,
    DEBUG=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class EmailPortalConfiguradoTests(MockResendMixin, TestCase):
    def test_portal_completo_continua_com_urls_do_tenant(self):
        portal = Portal.objects.create(
            nome='Jornal Completo',
            slug='jornal-completo-mail',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        usuario = User.objects.create_user('mail_ok', 'mail-ok@test.com', 'senha-temporaria-xyz')
        resultado = enviar_acesso(usuario, portal)
        self.assertTrue(resultado.ok)
        payload = self.resend_payloads[-1]
        self.assertEqual(payload['subject'], 'Acesso ao Jornal Completo')
        corpo = payload['text']
        self.assertIn('Seu portal foi criado com sucesso.', corpo)
        self.assertIn('https://jornal-completo-mail.portalnoticias.com.br/', corpo)
        self.assertIn('https://jornal-completo-mail.portalnoticias.com.br/app/', corpo)
        self.assertIn('/senha/redefinir/', corpo)
        self.assertNotIn('senha-temporaria-xyz', corpo)
        self.assertNotIn('configuração inicial', corpo.lower())
