"""Fase 3: gate de /app/ enquanto setup_concluido=False."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from plataforma.models import Membership, Portal
from plataforma.views_app import AppAccessMixin, AppComecarView

User = get_user_model()


def _host(slug, base='test'):
    return {'HTTP_HOST': f'{slug}.{base}'}


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=False,
    TENANT_BASE_DOMAIN='test',
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class AppOnboardingGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.incompleto = Portal.objects.create(
            nome='Portal Gate Incompleto',
            slug='portal-gate-incompleto',
            cidade='Campinas',
            estado='SP',
            status=Portal.STATUS_ATIVO,
            setup_concluido=False,
        )
        cls.completo = Portal.objects.create(
            nome='Portal Gate Completo',
            slug='portal-gate-completo',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        cls.outro = Portal.objects.create(
            nome='Portal Gate Outro',
            slug='portal-gate-outro',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=False,
        )
        plano = Portal.objects.filter(slug='plano-basico').first()
        if plano is None:
            plano = Portal.objects.create(
                nome='Notícias',
                slug='plano-basico',
                cidade='Campinas',
                estado='SP',
                status=Portal.STATUS_ATIVO,
                setup_concluido=True,
            )
        cls.plano_basico = plano
        cls.admin = User.objects.create_user('gate_admin', password='senha-forte-g1')
        cls.admin_completo = User.objects.create_user('gate_ok', password='senha-forte-g2')
        cls.admin_outro = User.objects.create_user('gate_outro', password='senha-forte-g3')
        cls.admin_plano = User.objects.create_user('gate_plano', password='senha-forte-g4')
        cls.master = User.objects.create_superuser(
            'gate_master', 'gatem@test.com', 'senha-forte-m1',
        )
        Membership.objects.create(
            usuario=cls.admin, portal=cls.incompleto, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.admin_completo, portal=cls.completo, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.admin_outro, portal=cls.outro, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.admin_plano, portal=cls.plano_basico, papel=Membership.PAPEL_ADMIN,
        )

    def _login(self, user, portal):
        self.client.force_login(user)
        self.client.defaults.update(_host(portal.slug))

    def _assert_vai_para_comecar(self, path):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 302, path)
        self.assertEqual(resp['Location'], reverse('app_comecar'))
        self.assertEqual(resp.get('Location'), '/app/comecar/')

    def test_mixin_cobre_views_do_app(self):
        self.assertTrue(issubclass(AppComecarView, AppAccessMixin))
        self.assertTrue(AppComecarView.permite_onboarding_incompleto)
        self.assertEqual(AppAccessMixin.URL_ONBOARDING, 'app_comecar')

    def test_incompleto_app_home_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_home'))

    def test_incompleto_noticias_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_noticias'))

    def test_incompleto_categorias_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_categorias'))

    def test_incompleto_publicidade_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_publicidade'))

    def test_incompleto_aparencia_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_aparencia'))

    def test_incompleto_assinatura_redireciona_comecar(self):
        self._login(self.admin, self.incompleto)
        self._assert_vai_para_comecar(reverse('app_assinatura'))

    def test_comecar_incompleto_200_sem_loop(self):
        self._login(self.admin, self.incompleto)
        resp = self.client.get(reverse('app_comecar'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.get('Location', ''), reverse('app_comecar'))
        self.assertContains(resp, 'Configure seu portal')

    def test_completo_app_home_normal(self):
        self._login(self.admin_completo, self.completo)
        resp = self.client.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 200)

    def test_completo_noticias_normal(self):
        self._login(self.admin_completo, self.completo)
        resp = self.client.get(reverse('app_noticias'))
        self.assertEqual(resp.status_code, 200)

    def test_completo_aparencia_normal(self):
        self._login(self.admin_completo, self.completo)
        resp = self.client.get(reverse('app_aparencia'))
        self.assertEqual(resp.status_code, 200)

    def test_master_nao_fica_preso_e_master_funciona(self):
        self.client.force_login(self.master)
        self.client.defaults.update(_host(self.incompleto.slug))
        resp_app = self.client.get(reverse('app_home'))
        self.assertEqual(resp_app.status_code, 200)
        self.assertNotEqual(resp_app.get('Location', ''), reverse('app_comecar'))
        resp_master = self.client.get(reverse('master_home'), HTTP_HOST='localhost')
        self.assertEqual(resp_master.status_code, 200)

    def test_anonimo_app_exige_autenticacao(self):
        resp = self.client.get(reverse('app_home'), **_host(self.incompleto.slug))
        self.assertEqual(resp.status_code, 302)
        location = resp['Location']
        self.assertTrue(location.startswith(reverse('entrar')))
        self.assertNotEqual(location, reverse('app_comecar'))
        self.assertIn('/entrar/', location)

    def test_next_nao_bypass_onboarding(self):
        self._login(self.admin, self.incompleto)
        resp = self.client.get(reverse('app_noticias'), {'next': reverse('app_noticias')})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('app_comecar'))
        resp_home = self.client.get(
            reverse('app_home'),
            {'next': reverse('app_aparencia')},
        )
        self.assertEqual(resp_home['Location'], reverse('app_comecar'))

    def test_nao_configura_outro_portal_por_parametro(self):
        self._login(self.admin, self.incompleto)
        resp = self.client.get(
            reverse('app_home'),
            {'portal_id': self.outro.pk, 'slug': self.outro.slug},
        )
        self.assertEqual(resp['Location'], reverse('app_comecar'))
        self._login(self.admin, self.outro)
        resp_host = self.client.get(
            reverse('app_comecar'),
            {'portal_id': self.outro.pk},
        )
        self.assertEqual(resp_host.status_code, 403)
        self.outro.refresh_from_db()
        self.assertFalse(self.outro.setup_concluido)
        self.assertEqual(self.outro.slug, 'portal-gate-outro')

    def test_plano_basico_legado_acessa_app(self):
        self.plano_basico.refresh_from_db()
        self.assertEqual(self.plano_basico.slug, 'plano-basico')
        self.assertTrue(self.plano_basico.setup_concluido)
        self._login(self.admin_plano, self.plano_basico)
        resp = self.client.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.get('Location', ''), reverse('app_comecar'))
        publico = self.client.get('/', **_host(self.plano_basico.slug))
        self.assertEqual(publico.status_code, 200)
