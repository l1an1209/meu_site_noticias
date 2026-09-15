"""Redirecionamento pós-login e seleção de portal."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from plataforma.models import Membership, Portal

User = get_user_model()


def _host(slug):
    return {'HTTP_HOST': f'{slug}.test'}


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class PosLoginRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legado = Portal.objects.get(slug=Portal.SLUG_LEGADO)
        cls.portal_a = Portal.objects.create(
            nome='Portal Um Pos',
            slug='pos-um',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
        )
        cls.portal_b = Portal.objects.create(
            nome='Portal Dois Pos',
            slug='pos-dois',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
        )
        cls.portal_bloq = Portal.objects.create(
            nome='Portal Bloq Pos',
            slug='pos-bloq',
            cidade='Ariquemes',
            estado='RO',
            status=Portal.STATUS_BLOQUEADO,
        )
        cls.master = User.objects.create_superuser('pos_master', 'posm@test.com', 'senha-forte-m1')
        cls.cliente_um = User.objects.create_user('pos_um', password='senha-forte-u1')
        cls.cliente_dois = User.objects.create_user('pos_dois', password='senha-forte-d1')
        cls.cliente_bloq = User.objects.create_user('pos_bloq', password='senha-forte-b1')
        cls.sem_portal = User.objects.create_user('pos_sem', password='senha-forte-s1')
        cls.outro = User.objects.create_user('pos_outro', password='senha-forte-o1')
        Membership.objects.create(
            usuario=cls.cliente_um, portal=cls.portal_a, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.cliente_dois, portal=cls.portal_a, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.cliente_dois, portal=cls.portal_b, papel=Membership.PAPEL_EDITOR,
        )
        Membership.objects.create(
            usuario=cls.cliente_bloq, portal=cls.portal_bloq, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.outro, portal=cls.portal_b, papel=Membership.PAPEL_ADMIN,
        )

    def _login(self, username, password, **host):
        return self.client.post(
            reverse('entrar'),
            {'username': username, 'password': password},
            **host,
        )

    def test_superuser_vai_para_master(self):
        resp = self._login('pos_master', 'senha-forte-m1', HTTP_HOST='localhost')
        self.assertRedirects(resp, reverse('master_home'), fetch_redirect_response=False)
        self.client.force_login(self.master)
        home = self.client.get(reverse('master_home'), HTTP_HOST='localhost')
        self.assertEqual(home.status_code, 200)

    def test_cliente_um_portal_vai_para_app_do_proprio_host(self):
        resp = self._login('pos_um', 'senha-forte-u1', **_host(self.portal_a.slug))
        self.assertRedirects(resp, reverse('app_home'), fetch_redirect_response=False)
        self.client.force_login(self.cliente_um)
        painel = self.client.get(reverse('app_home'), **_host(self.portal_a.slug))
        self.assertEqual(painel.status_code, 200)
        self.assertContains(painel, self.portal_a.nome)

    def test_cliente_dois_portais_vai_para_selecao(self):
        resp = self._login('pos_dois', 'senha-forte-d1', HTTP_HOST='localhost')
        self.assertRedirects(resp, reverse('selecionar_portal'), fetch_redirect_response=False)
        self.client.force_login(self.cliente_dois)
        pagina = self.client.get(reverse('selecionar_portal'), HTTP_HOST='localhost')
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, self.portal_a.nome)
        self.assertContains(pagina, self.portal_b.nome)
        self.assertNotContains(pagina, self.portal_bloq.nome)

    def test_cliente_escolhe_portal_a_e_acessa_app(self):
        self.client.force_login(self.cliente_dois)
        resp = self.client.post(
            reverse('selecionar_portal'),
            {'portal': self.portal_a.pk},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('app_home'))
        painel = self.client.get(reverse('app_home'), HTTP_HOST='localhost')
        self.assertEqual(painel.status_code, 200)
        self.assertContains(painel, self.portal_a.nome)

    def test_cliente_escolhe_portal_b_e_acessa_app(self):
        self.client.force_login(self.cliente_dois)
        resp = self.client.post(
            reverse('selecionar_portal'),
            {'portal': self.portal_b.pk},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('app_home'))
        painel = self.client.get(reverse('app_home'), HTTP_HOST='localhost')
        self.assertEqual(painel.status_code, 200)
        self.assertContains(painel, self.portal_b.nome)

    def test_cliente_nao_acessa_portal_de_outro(self):
        self.client.force_login(self.cliente_um)
        resp = self.client.post(
            reverse('selecionar_portal'),
            {'portal': self.portal_b.pk},
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 403)
        painel = self.client.get(reverse('app_home'), **_host(self.portal_b.slug))
        self.assertEqual(painel.status_code, 403)

    def test_sem_membership_vai_para_comece(self):
        resp = self._login('pos_sem', 'senha-forte-s1', HTTP_HOST='localhost')
        self.assertRedirects(resp, reverse('pagina_vendas'), fetch_redirect_response=False)

    def test_portal_bloqueado_nao_entra_no_app(self):
        resp = self._login('pos_bloq', 'senha-forte-b1', HTTP_HOST='localhost')
        self.assertRedirects(
            resp, reverse('acesso_portal_indisponivel'), fetch_redirect_response=False,
        )
        self.client.force_login(self.cliente_bloq)
        painel = self.client.get(reverse('app_home'), **_host(self.portal_bloq.slug))
        self.assertEqual(painel.status_code, 403)

    def test_next_master_nao_libera_cliente(self):
        resp = self.client.post(
            reverse('entrar') + '?next=/master/',
            {'username': 'pos_sem', 'password': 'senha-forte-s1', 'next': '/master/'},
            HTTP_HOST='localhost',
        )
        self.assertRedirects(resp, reverse('pagina_vendas'), fetch_redirect_response=False)
        self.client.force_login(self.sem_portal)
        self.assertEqual(self.client.get(reverse('master_home'), HTTP_HOST='localhost').status_code, 403)

    def test_next_app_nao_libera_sem_permissao(self):
        resp = self.client.post(
            reverse('entrar') + '?next=/app/',
            {'username': 'pos_sem', 'password': 'senha-forte-s1', 'next': '/app/'},
            HTTP_HOST='localhost',
        )
        self.assertRedirects(resp, reverse('pagina_vendas'), fetch_redirect_response=False)
        self.client.force_login(self.sem_portal)
        self.assertRedirects(
            self.client.get(reverse('app_home'), HTTP_HOST='localhost'),
            reverse('pagina_vendas'),
            fetch_redirect_response=False,
        )

    def test_next_externo_bloqueado(self):
        resp = self.client.post(
            reverse('entrar'),
            {
                'username': 'pos_sem',
                'password': 'senha-forte-s1',
                'next': 'https://evil.example/phish',
            },
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp['Location'])
        self.assertRedirects(resp, reverse('pagina_vendas'), fetch_redirect_response=False)

    def test_cadastro_novo_usuario_vai_para_comece(self):
        resp = self.client.post(
            reverse('cadastro'),
            {
                'username': 'pos_novo',
                'email': 'posnovo@test.com',
                'password1': 'senha-forte-n1',
                'password2': 'senha-forte-n1',
                'tipo_conta': 'morador',
            },
            HTTP_HOST='localhost',
        )
        self.assertRedirects(resp, reverse('pagina_vendas'), fetch_redirect_response=False)
        user = User.objects.get(username='pos_novo')
        self.assertTrue(user.is_authenticated)
        self.assertFalse(user.memberships.exists())

    def test_app_protegido_acesso_direto(self):
        self.assertEqual(self.client.get(reverse('app_home'), HTTP_HOST='localhost').status_code, 302)
        self.client.force_login(self.sem_portal)
        self.assertRedirects(
            self.client.get(reverse('app_home'), HTTP_HOST='localhost'),
            reverse('pagina_vendas'),
            fetch_redirect_response=False,
        )

    def test_fallback_local_respeita_membership_do_legado(self):
        user = User.objects.create_user('pos_legado', password='senha-forte-l1')
        Membership.objects.create(
            usuario=user, portal=self.legado, papel=Membership.PAPEL_ADMIN,
        )
        resp = self._login('pos_legado', 'senha-forte-l1', HTTP_HOST='localhost')
        self.assertRedirects(resp, reverse('app_home'), fetch_redirect_response=False)
        self.client.force_login(user)
        painel = self.client.get(reverse('app_home'), HTTP_HOST='localhost')
        self.assertEqual(painel.status_code, 200)

    def test_localhost_abre_app_do_unico_portal_do_cliente(self):
        resp = self._login('pos_um', 'senha-forte-u1', HTTP_HOST='localhost')
        self.assertRedirects(resp, reverse('app_home'), fetch_redirect_response=False)
        self.client.force_login(self.cliente_um)
        painel = self.client.get(reverse('app_home'), HTTP_HOST='localhost')
        self.assertEqual(painel.status_code, 200)
        self.assertContains(painel, self.portal_a.nome)
        self.assertNotContains(painel, self.legado.nome)

    def test_next_conta_permitido(self):
        resp = self.client.post(
            reverse('entrar'),
            {'username': 'pos_sem', 'password': 'senha-forte-s1', 'next': '/conta/'},
            HTTP_HOST='localhost',
        )
        self.assertRedirects(resp, '/conta/', fetch_redirect_response=False)
