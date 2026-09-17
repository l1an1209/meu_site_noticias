"""Isolamento multi-tenant: dois portais e provas de IDOR, papéis e master."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Anuncio, Categoria, Contribuicao, Noticia
from plataforma.models import Membership, Portal


User = get_user_model()


def _host(slug):
    return f'{slug}.test'


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class IsolamentoDoisTenantsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.portal_a = Portal.objects.create(
            nome='Portal Alfa',
            slug='portala',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        cls.portal_b = Portal.objects.create(
            nome='Portal Beta',
            slug='portalb',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        cls.cat_a = Categoria.all_objects.create(
            portal=cls.portal_a, nome='Geral', slug='geral',
        )
        cls.cat_b = Categoria.all_objects.create(
            portal=cls.portal_b, nome='Geral', slug='geral',
        )
        cls.noticia_a = Noticia.all_objects.create(
            portal=cls.portal_a,
            categoria=cls.cat_a,
            titulo='Segredo exclusivo Alfa',
            conteudo='Conteúdo só do portal A',
        )
        cls.noticia_b = Noticia.all_objects.create(
            portal=cls.portal_b,
            categoria=cls.cat_b,
            titulo='Segredo exclusivo Beta',
            conteudo='Conteúdo só do portal B',
        )
        Anuncio.all_objects.create(
            portal=cls.portal_a,
            slot='feed',
            titulo_interno='Anunciante-Alfa',
            ativo=True,
            codigo_html='<span>Anunciante-Alfa</span>',
        )
        Anuncio.all_objects.create(
            portal=cls.portal_b,
            slot='feed',
            titulo_interno='Anunciante-Beta',
            ativo=True,
            codigo_html='<span>Anunciante-Beta</span>',
        )
        cls.envio_a = Contribuicao.all_objects.create(
            portal=cls.portal_a,
            titulo='Envio Alfa',
            conteudo='Texto A',
            nome='Morador A',
            email='a@test.com',
            status='pendente',
        )
        cls.envio_b = Contribuicao.all_objects.create(
            portal=cls.portal_b,
            titulo='Envio Beta',
            conteudo='Texto B',
            nome='Morador B',
            email='b@test.com',
            status='pendente',
        )

        cls.user_a = User.objects.create_user('admin_a', password='pass-a', is_staff=True)
        cls.user_b = User.objects.create_user('admin_b', password='pass-b', is_staff=True)
        cls.editor_a = User.objects.create_user('editor_a', password='pass-e', is_staff=True)
        cls.autor_a = User.objects.create_user('autor_a', password='pass-r', is_staff=True)
        cls.moderador_a = User.objects.create_user('mod_a', password='pass-m', is_staff=True)
        cls.master = User.objects.create_superuser('master', 'master@test.com', 'pass-master')

        Membership.objects.create(
            usuario=cls.user_a, portal=cls.portal_a, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.user_b, portal=cls.portal_b, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.editor_a, portal=cls.portal_a, papel=Membership.PAPEL_EDITOR,
        )
        Membership.objects.create(
            usuario=cls.autor_a, portal=cls.portal_a, papel=Membership.PAPEL_AUTOR,
        )
        Membership.objects.create(
            usuario=cls.moderador_a, portal=cls.portal_a, papel=Membership.PAPEL_MODERADOR,
        )

    def _client(self, slug, user=None):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        self.client.defaults['HTTP_HOST'] = _host(slug)
        return self.client

    def test_08_existem_dois_tenants_de_teste(self):
        self.assertNotEqual(self.portal_a.pk, self.portal_b.pk)
        self.assertEqual(Portal.objects.filter(slug__in=['portala', 'portalb']).count(), 2)

    def test_01_listagem_do_portal_a_nao_mostra_noticias_do_b(self):
        resp = self._client('portala').get('/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Segredo exclusivo Alfa', body)
        self.assertNotIn('Segredo exclusivo Beta', body)

    def test_01_listagem_do_portal_b_nao_mostra_noticias_do_a(self):
        resp = self._client('portalb').get('/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Segredo exclusivo Beta', body)
        self.assertNotIn('Segredo exclusivo Alfa', body)

    def test_02_idor_url_noticia_b_no_host_a_retorna_404(self):
        resp = self._client('portala').get(f'/noticia/{self.noticia_b.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_02_noticia_a_no_host_a_retorna_200(self):
        resp = self._client('portala').get(f'/noticia/{self.noticia_a.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Segredo exclusivo Alfa')

    def test_05_busca_no_portal_a_nao_acha_titulo_do_b(self):
        resp = self._client('portala').get('/?q=Segredo+exclusivo+Beta')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, f'/noticia/{self.noticia_b.pk}/')
        self.assertNotContains(resp, 'Conteúdo só do portal B')

    def test_05_categoria_mesmo_slug_nao_mistura_noticias(self):
        resp = self._client('portala').get('/categoria/geral/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Segredo exclusivo Alfa')
        self.assertNotContains(resp, 'Segredo exclusivo Beta')

    def test_05_anuncio_do_portal_a_nao_exibe_anunciante_b(self):
        resp = self._client('portala').get('/')
        self.assertNotContains(resp, 'Anunciante-Beta')

    def test_05_envios_no_painel_a_nao_listam_envio_b(self):
        resp = self._client('portala', self.user_a).get('/painel/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Envio Alfa', body)
        self.assertNotIn('Envio Beta', body)

    def test_03_admin_a_abre_noticia_propria_e_nao_a_do_b(self):
        url_a = reverse('admin:noticias_noticia_change', args=[self.noticia_a.pk])
        url_b = reverse('admin:noticias_noticia_change', args=[self.noticia_b.pk])
        client = self._client('portala', self.user_a)
        resp_a = client.get(url_a)
        self.assertEqual(resp_a.status_code, 200, resp_a.get('Location'))
        self.assertContains(resp_a, 'Segredo exclusivo Alfa')
        resp_b = client.get(url_b)
        self.assertNotEqual(
            resp_b.status_code,
            200,
            'Admin do portal A não pode abrir o formulário da notícia do portal B',
        )
        self.assertIn(resp_b.status_code, (302, 403, 404))

    def test_03_admin_a_nao_exclui_noticia_b(self):
        url = reverse('admin:noticias_noticia_delete', args=[self.noticia_b.pk])
        resp = self._client('portala', self.user_a).post(url, {'post': 'yes'})
        self.assertNotEqual(resp.status_code, 200)
        self.assertTrue(Noticia.all_objects.filter(pk=self.noticia_b.pk).exists())

    def test_03_aprovar_envio_b_pelo_host_a_retorna_404(self):
        resp = self._client('portala', self.user_a).post(
            f'/painel/aprovar/{self.envio_b.pk}/',
        )
        self.assertEqual(resp.status_code, 404)
        self.envio_b.refresh_from_db()
        self.assertEqual(self.envio_b.status, 'pendente')

    def test_03_rejeitar_envio_b_pelo_host_a_retorna_404(self):
        resp = self._client('portala', self.user_a).post(
            f'/painel/rejeitar/{self.envio_b.pk}/',
        )
        self.assertEqual(resp.status_code, 404)

    def test_04_api_curtir_noticia_b_no_host_a_retorna_404(self):
        resp = self._client('portala', self.user_a).post(
            f'/noticia/{self.noticia_b.pk}/curtir/',
        )
        self.assertEqual(resp.status_code, 404)

    def test_04_api_comentar_noticia_b_no_host_a_retorna_404(self):
        resp = self._client('portala', self.user_a).post(
            f'/noticia/{self.noticia_b.pk}/comentar/',
            {'texto': 'tentativa cruzada'},
        )
        self.assertEqual(resp.status_code, 404)

    def test_04_api_clima_responde_cidade_do_host(self):
        from unittest.mock import MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"current":{"temperature_2m":20}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with patch('noticias.views_experiencia.urlopen', return_value=mock_resp):
            resp = self._client('portalb').get('/api/clima/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('cidade'), 'Vilhena')

    def test_05_sitemap_do_portal_a_nao_inclui_id_do_b(self):
        resp = self._client('portala').get('/sitemap.xml')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f'/noticia/{self.noticia_a.pk}/', body)
        self.assertNotIn(f'/noticia/{self.noticia_b.pk}/', body)

    def test_06_editor_nao_acessa_painel_de_moderacao(self):
        resp = self._client('portala', self.editor_a).get('/painel/')
        self.assertEqual(resp.status_code, 403)

    def test_06_autor_nao_acessa_painel_de_moderacao(self):
        resp = self._client('portala', self.autor_a).get('/painel/')
        self.assertEqual(resp.status_code, 403)

    def test_06_moderador_acessa_painel_do_proprio_portal(self):
        resp = self._client('portala', self.moderador_a).get('/painel/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Envio Alfa')
        self.assertNotContains(resp, 'Envio Beta')

    def test_06_admin_a_nao_acessa_painel_no_host_b(self):
        resp = self._client('portalb', self.user_a).get('/painel/')
        self.assertEqual(resp.status_code, 403)

    def test_06_editor_nao_abre_modulo_anuncio(self):
        url = reverse('admin:noticias_anuncio_changelist')
        resp = self._client('portala', self.editor_a).get(url)
        self.assertIn(resp.status_code, (403, 302))

    def test_06_autor_nao_abre_modulo_contribuicao(self):
        url = reverse('admin:noticias_contribuicao_changelist')
        resp = self._client('portala', self.autor_a).get(url)
        self.assertIn(resp.status_code, (403, 302))

    def test_07_master_ve_noticia_b_no_admin(self):
        url = reverse('admin:noticias_noticia_change', args=[self.noticia_b.pk])
        resp = self._client('portala', self.master).get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Segredo exclusivo Beta')

    def test_07_master_lista_admin_inclui_os_dois_portais(self):
        url = reverse('admin:noticias_noticia_changelist')
        resp = self._client('portala', self.master).get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Segredo exclusivo Alfa', body)
        self.assertIn('Segredo exclusivo Beta', body)

    def test_07_master_nao_mistura_site_publico(self):
        resp = self._client('portala', self.master).get('/')
        self.assertContains(resp, 'Segredo exclusivo Alfa')
        self.assertNotContains(resp, 'Segredo exclusivo Beta')

    def test_compat_fallback_nao_e_usado_quando_host_identifica_tenant(self):
        resp = self._client('portala').get('/')
        self.assertFalse(resp.wsgi_request.portal_from_compat_fallback)
        self.assertEqual(resp.wsgi_request.portal.pk, self.portal_a.pk)
