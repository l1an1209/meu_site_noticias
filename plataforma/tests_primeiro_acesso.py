"""Fluxo obrigatório de primeiro acesso. Sem migration."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Categoria, Noticia
from plataforma.models import AuditLog, Membership, Portal
from plataforma.services.primeiro_acesso import url_noticia_publica, url_whatsapp

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=False,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class PrimeiroAcessoTests(TestCase):
    def setUp(self):
        self.portal = Portal.objects.create(
            nome='Portal Novo',
            slug='portal-novo',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
            slogan='Notícias da sua cidade',
        )
        self.outro = Portal.objects.create(
            nome='Outro Portal',
            slug='portal-outro',
            cidade='Ji-Paraná',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        self.user = User.objects.create_user('cliente-novo', password='x')
        Membership.objects.create(usuario=self.user, portal=self.portal, papel=Membership.PAPEL_ADMIN)
        AuditLog.objects.create(portal=self.portal, usuario=self.user, acao='primeiro_acesso', objeto='Portal', objeto_id=str(self.portal.pk))
        self.client.force_login(self.user)

    def _host(self, portal=None):
        portal = portal or self.portal
        return {'HTTP_HOST': f'{portal.slug}.test'}

    def _aparencia(self):
        return {
            'nome': 'Portal Novo',
            'cidade': 'Cacoal',
            'estado': 'RO',
            'slogan': 'A cidade em primeiro lugar',
            'tagline': 'Notícias locais',
            'descricao': 'O portal da cidade.',
            'cor_primaria': '#0d9488',
            'cor_secundaria': '#1a365d',
            'cor_destaque': '#ea580c',
        }

    def test_cliente_existente_entra_no_painel(self):
        antigo = Portal.objects.create(
            nome='Portal Antigo', slug='portal-antigo', cidade='Cacoal', estado='RO',
            status=Portal.STATUS_ATIVO, setup_concluido=True,
        )
        Membership.objects.create(usuario=self.user, portal=antigo, papel=Membership.PAPEL_ADMIN)
        Categoria.all_objects.create(portal=antigo, nome='Geral', slug='geral')
        Noticia.all_objects.create(portal=antigo, titulo='Ja publicada', conteudo='Texto')
        resp = self.client.get('/app/', **self._host(antigo))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Seu portal está no ar')
        self.assertNotContains(resp, 'Comece por aqui')

    def test_app_bloqueado_ate_concluir_e_url_do_proprio_portal(self):
        resp = self.client.get('/app/', **self._host())
        self.assertRedirects(resp, reverse('app_aparencia'), fetch_redirect_response=False)
        self.client.get('/app/configuracoes/', **self._host())
        self.assertEqual(
            self.client.get('/app/configuracoes/', **self._host()).status_code,
            302,
        )

        salvo = self.client.post(reverse('app_aparencia'), self._aparencia(), **self._host())
        self.assertRedirects(salvo, reverse('app_categorias'), fetch_redirect_response=False)
        self.portal.refresh_from_db()
        self.assertEqual(self.portal.tagline, 'Notícias locais')
        self.outro.refresh_from_db()
        self.assertNotEqual(self.outro.tagline, 'Notícias locais')

        categorias = self.client.get(reverse('app_categorias'), **self._host())
        self.assertEqual(categorias.status_code, 200)
        self.assertContains(categorias, 'Notícias')
        self.assertTrue(Categoria.all_objects.filter(portal=self.portal, slug='noticias').exists())
        self.assertFalse(Categoria.all_objects.filter(portal=self.outro, slug='noticias').exists())

        seguir = self.client.post(reverse('app_categorias'), {}, **self._host())
        self.assertRedirects(seguir, reverse('app_noticia_nova'), fetch_redirect_response=False)

        publicada = self.client.post(reverse('app_noticia_nova'), {
            'titulo': 'Primeira do novo',
            'conteudo': 'Texto da estreia.',
            'autor': 'Redação',
        }, **self._host())
        self.assertRedirects(publicada, reverse('app_ativar'), fetch_redirect_response=False)
        noticia = Noticia.all_objects.get(portal=self.portal, titulo='Primeira do novo')
        self.assertFalse(Noticia.all_objects.filter(portal=self.outro, titulo='Primeira do novo').exists())

        pagina = self.client.get(reverse('app_ativar'), **self._host())
        self.assertContains(pagina, 'Sua primeira notícia foi publicada!')
        link = url_noticia_publica(self.portal, noticia)
        self.assertIn(link, pagina.content.decode())
        self.assertIn('portal-novo.test', link)
        self.assertNotIn('portal-outro.test', link)
        self.assertIn('wa.me', url_whatsapp(self.portal, noticia))
        self.assertIn('portal-novo.test', url_whatsapp(self.portal, noticia))

        self.assertEqual(self.client.get('/app/', **self._host()).status_code, 302)
        viu = self.client.post(reverse('app_ativar'), {'acao': 'viu'}, **self._host())
        self.assertRedirects(viu, reverse('app_ativar'), fetch_redirect_response=False)
        share = self.client.get(reverse('app_ativar'), **self._host())
        self.assertContains(share, 'Copiar link')
        self.assertContains(share, 'navigator.share')
        self.assertContains(share, 'Compartilhar no WhatsApp')

        fim = self.client.post(reverse('app_ativar'), {'acao': 'compartilhar', 'canal': 'copiar'}, **self._host())
        self.assertIn('pronto=1', fim['Location'])
        pronto = self.client.get(fim['Location'], **self._host())
        self.assertContains(pronto, 'Portal pronto!')
        self.assertContains(pronto, 'Link copiado!')
        painel = self.client.get('/app/', **self._host())
        self.assertEqual(painel.status_code, 200)
        self.assertContains(painel, 'Seu portal está no ar')

        self.client.get('/sair/', **self._host())
        self.client.force_login(self.user)
        de_novo = self.client.get('/app/', **self._host())
        self.assertEqual(de_novo.status_code, 200)
        self.assertNotContains(de_novo, 'Agora compartilhe')
