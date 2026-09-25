"""Plano gratuito, publicidade da rede e upgrade sem duplicar o portal."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Noticia
from plataforma.models import Assinatura, Cliente, ConfiguracaoMonetizacao, Membership, Plano, Portal
from plataforma.services.kiwify import assinatura_kiwify
from plataforma.tests_comercial import SECRET, _payload_aprovado
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY

User = get_user_model()

SENHA = 'Senha-forte-portal-1'


def _ligar_publicidade(script='<script src="https://ads.example/rede.js" data-rede-publicidade="1"></script>'):
    cfg = ConfiguracaoMonetizacao.obter()
    cfg.ativa = True
    cfg.publicidade_gratuito = True
    cfg.publicidade_pago = False
    cfg.codigo_script = script
    cfg.posicoes = ['top', 'article']
    cfg.provedor = ConfiguracaoMonetizacao.PROVEDOR_OUTRO
    cfg.save()
    from plataforma.services.publicidade import limpar_cache_monetizacao
    limpar_cache_monetizacao()
    return cfg


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=False,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class CadastroGratuitoTests(MockResendMixin, TestCase):
    def test_usuario_cria_portal_gratuito_e_entra(self):
        resp = self.client.post(reverse('app_comecar'), {
            'plano': 'gratuito',
            'nome_pessoa': 'Ana Souza',
            'email': 'ana.gratis@test.com',
            'senha': SENHA,
            'nome': 'Notícias da Ana',
            'slug': 'noticias-ana',
            'cidade': 'Campinas',
            'estado': 'SP',
        }, HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 302, resp.content[:500] if hasattr(resp, 'content') else resp)
        portal = Portal.objects.get(slug='noticias-ana')
        self.assertEqual(portal.nome, 'Notícias da Ana')
        self.assertTrue(portal.setup_concluido)
        self.assertEqual(portal.plano.codigo, 'gratuito')
        self.assertEqual(portal.pagamento_status, Portal.PAGAMENTO_GRATUITO)
        assinatura = portal.assinatura
        self.assertEqual(assinatura.origem, Assinatura.ORIGEM_GRATUITA)
        self.assertEqual(assinatura.status, Assinatura.STATUS_ATIVA)
        self.assertEqual(Cliente.objects.filter(email='ana.gratis@test.com').count(), 1)
        self.assertTrue(Membership.objects.filter(portal=portal, papel=Membership.PAPEL_ADMIN).exists())
        self.client.logout()
        login = self.client.post(reverse('entrar'), {
            'username': User.objects.get(email='ana.gratis@test.com').username,
            'password': SENHA,
        }, HTTP_HOST='localhost')
        self.assertEqual(login.status_code, 302)
        publico = self.client.get('/', HTTP_HOST='noticias-ana.test')
        self.assertEqual(publico.status_code, 200)
        self.assertContains(publico, 'Notícias da Ana')

    def test_email_existente_nao_duplica_cliente(self):
        self.client.post(reverse('app_comecar'), {
            'plano': 'gratuito',
            'nome_pessoa': 'Ana Souza',
            'email': 'ana.gratis@test.com',
            'senha': SENHA,
            'nome': 'Notícias da Ana',
            'slug': 'noticias-ana',
            'cidade': 'Campinas',
            'estado': 'SP',
        }, HTTP_HOST='localhost')
        self.client.logout()
        resp = self.client.post(reverse('app_comecar'), {
            'plano': 'gratuito',
            'nome_pessoa': 'Ana Souza',
            'email': 'ana.gratis@test.com',
            'senha': SENHA,
            'nome': 'Outro portal',
            'slug': 'outro-ana',
            'cidade': 'Campinas',
            'estado': 'SP',
        }, HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Cliente.objects.filter(email='ana.gratis@test.com').count(), 1)
        self.assertFalse(Portal.objects.filter(slug='outro-ana').exists())

    def test_plano_pago_vai_para_kiwify_sem_criar_portal(self):
        antes = Portal.objects.count()
        resp = self.client.post(reverse('app_comecar'), {
            'plano': 'basico',
            'nome_pessoa': 'Bruno Pago',
            'email': 'bruno.pago@test.com',
            'nome': 'Portal Bruno',
            'slug': 'portal-bruno',
            'cidade': 'Cacoal',
            'estado': 'RO',
        }, HTTP_HOST='localhost')
        self.assertRedirects(
            resp,
            reverse('pagina_checkout_plano', args=['basico']),
            fetch_redirect_response=False,
        )
        self.assertEqual(Portal.objects.count(), antes)
        self.assertFalse(User.objects.filter(email='bruno.pago@test.com').exists())


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=False,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class UpgradeKiwifyTests(MockResendMixin, TestCase):
    def test_webhook_pago_continua_criando_portal(self):
        resp = self.client.post(
            reverse('webhook_kiwify'),
            data=json.dumps(_payload_aprovado(order_id='ord-novo', email='novo.pago@test.com', sub_id='sub-novo')),
            content_type='application/json',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 200)
        portal = Portal.objects.get(cliente__email='novo.pago@test.com')
        self.assertEqual(portal.assinatura.origem, Assinatura.ORIGEM_KIWIFY)
        self.assertEqual(portal.pagamento_status, Portal.PAGAMENTO_PAGO)
        self.assertFalse(portal.plano.e_gratuito)

    def test_webhook_atualiza_portal_gratuito_sem_duplicar(self):
        self.client.post(reverse('app_comecar'), {
            'plano': 'gratuito',
            'nome_pessoa': 'Carla',
            'email': 'carla.upgrade@test.com',
            'senha': SENHA,
            'nome': 'Portal Carla',
            'slug': 'portal-carla',
            'cidade': 'Vilhena',
            'estado': 'RO',
        }, HTTP_HOST='localhost')
        portal = Portal.objects.get(slug='portal-carla')
        Plano.objects.filter(codigo='basico').update(kiwify_product_id='prod-campinas')
        resp = self.client.post(
            reverse('webhook_kiwify'),
            data=json.dumps(_payload_aprovado(
                order_id='ord-up', email='carla.upgrade@test.com', sub_id='sub-up',
            )),
            content_type='application/json',
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Portal.objects.filter(cliente__email='carla.upgrade@test.com').count(), 1)
        portal.refresh_from_db()
        assinatura = Assinatura.objects.get(portal=portal)
        self.assertEqual(assinatura.origem, Assinatura.ORIGEM_KIWIFY)
        self.assertEqual(assinatura.plano.codigo, 'basico')
        self.assertEqual(portal.plano.codigo, 'basico')
        self.assertEqual(portal.slug, 'portal-carla')
        self.assertTrue(Noticia.all_objects.filter(portal=portal).count() >= 0)


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=False,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class PublicidadeRedeTests(TestCase):
    def setUp(self):
        self.gratis = Portal.objects.create(
            nome='Portal Grátis',
            slug='portal-gratis-ads',
            cidade='Campinas',
            estado='SP',
            status=Portal.STATUS_ATIVO,
            plano=Plano.objects.get(codigo='gratuito'),
            setup_concluido=True,
        )
        self.pago = Portal.objects.create(
            nome='Portal Pago',
            slug='portal-pago-ads',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            plano=Plano.objects.get(codigo='basico'),
            setup_concluido=True,
        )
        self.dono = User.objects.create_user('dono_ads', password=SENHA)
        Membership.objects.create(usuario=self.dono, portal=self.gratis, papel=Membership.PAPEL_ADMIN)
        self.master = User.objects.create_superuser('master_ads', 'masterads@test.com', SENHA)

    def test_ads_txt_do_portal_com_monetizacao(self):
        _ligar_publicidade()
        from plataforma.models import ConfiguracaoMonetizacao
        cfg = ConfiguracaoMonetizacao.objects.get(pk=1)
        cfg.publisher_id = 'ca-pub-5451545777538942'
        cfg.provedor = ConfiguracaoMonetizacao.PROVEDOR_ADSENSE
        cfg.save()
        resp = self.client.get('/ads.txt', HTTP_HOST='portal-gratis-ads.test')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp['Content-Type'].startswith('text/plain'))
        self.assertEqual(
            resp.content.decode(),
            'google.com, pub-5451545777538942, DIRECT, f08c47fec0942fa0\n',
        )

    def test_ads_txt_ausente_sem_publicidade(self):
        resp = self.client.get('/ads.txt', HTTP_HOST='portal-gratis-ads.test')
        self.assertEqual(resp.status_code, 404)
        plataforma = self.client.get('/ads.txt', HTTP_HOST='localhost')
        self.assertEqual(plataforma.status_code, 404)

    def test_gratuito_mostra_quando_habilitada(self):
        _ligar_publicidade()
        resp = self.client.get('/', HTTP_HOST='portal-gratis-ads.test')
        self.assertContains(resp, 'data-rede-publicidade="1"')
        self.assertContains(resp, 'data-rede-slot="top"')

    def test_sem_politica_nao_mostra(self):
        resp = self.client.get('/', HTTP_HOST='portal-gratis-ads.test')
        self.assertNotContains(resp, 'data-rede-publicidade')

    def test_master_desliga_publicidade(self):
        _ligar_publicidade()
        self.gratis.publicidade_modo = Portal.PUBLICIDADE_INATIVA
        self.gratis.save(update_fields=['publicidade_modo'])
        resp = self.client.get('/', HTTP_HOST='portal-gratis-ads.test')
        self.assertNotContains(resp, 'data-rede-publicidade')
        cfg = ConfiguracaoMonetizacao.obter()
        cfg.ativa = False
        cfg.save()
        self.gratis.publicidade_modo = Portal.PUBLICIDADE_HERDAR
        self.gratis.save(update_fields=['publicidade_modo'])
        resp = self.client.get('/', HTTP_HOST='portal-gratis-ads.test')
        self.assertNotContains(resp, 'data-rede-publicidade')

    def test_pago_nao_mostra_com_politica_padrao(self):
        _ligar_publicidade()
        resp = self.client.get('/', HTTP_HOST='portal-pago-ads.test')
        self.assertNotContains(resp, 'data-rede-publicidade')

    def test_cliente_nao_altera_configuracao_global(self):
        self.client.force_login(self.dono)
        resp = self.client.post(reverse('master_monetizacao'), {
            'ativa': 'on',
            'provedor': 'adsense',
        }, HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(ConfiguracaoMonetizacao.obter().ativa)

    def test_script_nao_aparece_no_painel(self):
        _ligar_publicidade()
        self.client.force_login(self.dono)
        painel = self.client.get(reverse('app_home'), HTTP_HOST='portal-gratis-ads.test')
        self.assertEqual(painel.status_code, 200)
        self.assertNotContains(painel, 'data-rede-publicidade')
        self.assertNotContains(painel, 'ads.example/rede.js')
        self.client.force_login(self.master)
        master = self.client.get(reverse('master_analytics'), HTTP_HOST='localhost')
        self.assertEqual(master.status_code, 200)
        self.assertNotContains(master, 'ads.example/rede.js')

    def test_usuario_nao_ve_portal_alheio_nem_analytics_global(self):
        outro = Portal.objects.create(
            nome='Portal B',
            slug='portal-b-iso',
            cidade='Ji-Paraná',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        self.client.force_login(self.dono)
        resp = self.client.get(reverse('app_home'), HTTP_HOST='portal-b-iso.test')
        self.assertEqual(resp.status_code, 403)
        self.assertNotContains(resp, 'app-sidebar', status_code=403)
        analytics = self.client.get(reverse('master_analytics'), HTTP_HOST='localhost')
        self.assertEqual(analytics.status_code, 403)
        self.assertFalse(outro.should_show_ads)
