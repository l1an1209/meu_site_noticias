"""Painel do cliente, master e páginas de erro (etapa 4)."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Categoria, Noticia
from plataforma.models import Membership, Portal

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class PainelUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legado = Portal.objects.get(slug=Portal.SLUG_LEGADO)
        cls.beta = Portal.objects.get(slug=Portal.SLUG_TESTE)
        cls.admin = User.objects.create_user('editor-a', password='x')
        Membership.objects.create(
            usuario=cls.admin, portal=cls.legado, papel=Membership.PAPEL_ADMIN,
        )
        cls.master = User.objects.create_superuser('root', 'root@test.com', 'x')
        cls.cat = Categoria.all_objects.create(
            portal=cls.legado, nome='Geral UI', slug='geral-ui',
        )

    def _host(self, slug):
        return {'HTTP_HOST': f'{slug}.test'}

    def test_home_publico_usa_design_system_e_cores_do_tenant(self):
        html = self.client.get('/', **self._host(self.legado.slug)).content.decode()
        self.assertIn('css/ds.css', html)
        self.assertIn('css/public.css', html)
        self.assertIn(self.legado.cor_primaria, html)
        self.assertIn(self.legado.nome, html)
        html_b = self.client.get('/', **self._host(self.beta.slug)).content.decode()
        self.assertIn(self.beta.cor_primaria, html_b)
        self.assertIn(self.beta.nome, html_b)
        self.assertNotIn(self.legado.nome, html_b)
        self.assertNotIn('Ji-Paraná', html_b)

    def test_app_exige_equipe_do_portal(self):
        resp = self.client.get('/app/', **self._host(self.legado.slug))
        self.assertEqual(resp.status_code, 302)
        self.client.force_login(self.admin)
        resp = self.client.get('/app/', **self._host(self.legado.slug))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Visão geral')
        self.assertContains(resp, 'Dashboard')
        resp_b = self.client.get('/app/', **self._host(self.beta.slug))
        self.assertEqual(resp_b.status_code, 403)

    def test_aparencia_altera_so_o_tenant_atual(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('app_aparencia'),
            {
                'nome': 'Marca Alfa UI',
                'cidade': self.legado.cidade,
                'estado': self.legado.estado,
                'slogan': 'Slogan novo A',
                'cor_primaria': '#112233',
                'cor_secundaria': '#223344',
                'cor_destaque': '#334455',
            },
            **self._host(self.legado.slug),
        )
        self.assertEqual(resp.status_code, 302)
        self.legado.refresh_from_db()
        self.beta.refresh_from_db()
        self.assertEqual(self.legado.nome, 'Marca Alfa UI')
        self.assertEqual(self.legado.cor_primaria, '#112233')
        self.assertNotEqual(self.beta.nome, 'Marca Alfa UI')
        html_b = self.client.get('/', **self._host(self.beta.slug)).content.decode()
        self.assertNotIn('Marca Alfa UI', html_b)
        self.assertNotIn('#112233', html_b)

    def test_criar_noticia_no_painel_fica_no_tenant(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('app_noticia_nova'),
            {
                'titulo': 'Materia painel A',
                'conteudo': 'Texto da matéria no painel.',
                'categoria': self.cat.pk,
                'autor': 'Redação',
            },
            **self._host(self.legado.slug),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Noticia.all_objects.filter(portal=self.legado, titulo='Materia painel A').exists()
        )
        self.assertFalse(
            Noticia.all_objects.filter(portal=self.beta, titulo='Materia painel A').exists()
        )

    def test_master_lista_portais_e_comum_nao_entra(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/master/', **self._host(self.legado.slug))
        self.assertEqual(resp.status_code, 403)
        self.client.force_login(self.master)
        resp = self.client.get('/master/', **self._host(self.legado.slug))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.legado.nome)
        self.assertContains(resp, self.beta.nome)
        self.assertContains(resp, 'Painel da plataforma')

    def test_paginas_de_erro(self):
        resp = self.client.get('/pagina-inexistente-xyz/', **self._host(self.legado.slug))
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, 'Não encontramos esta página', status_code=404)
        self.assertContains(resp, self.legado.nome, status_code=404)

    def test_login_nao_sobrescreve_nome_do_portal(self):
        resp = self.client.get('/entrar/', **self._host(self.legado.slug))
        self.assertContains(resp, f'Entrar — {self.legado.nome}')
        self.assertContains(resp, f'{self.legado.nome} — curtir')
