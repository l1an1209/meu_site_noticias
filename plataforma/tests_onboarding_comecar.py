"""Fase 2: tela /app/comecar/ — nome e slug únicos do portal."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.text import slugify

from plataforma.forms import AparenciaForm, PortalOnboardingForm
from plataforma.models import Membership, Portal
from plataforma.slugs import SLUGS_RESERVADOS

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
class AppComecarOnboardingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.portal = Portal.objects.create(
            nome='Portal Provisório',
            slug='portal-provisorio-onb',
            cidade='Campinas',
            estado='SP',
            status=Portal.STATUS_ATIVO,
            setup_concluido=False,
        )
        cls.ocupado = Portal.objects.create(
            nome='Já existe',
            slug='slug-ja-ocupado',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        cls.outro = Portal.objects.create(
            nome='Outro portal',
            slug='outro-portal-onb',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=False,
        )
        cls.admin = User.objects.create_user('onb_admin', password='senha-forte-a1')
        cls.editor = User.objects.create_user('onb_editor', password='senha-forte-e1')
        cls.admin_outro = User.objects.create_user('onb_outro', password='senha-forte-o1')
        Membership.objects.create(
            usuario=cls.admin, portal=cls.portal, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.editor, portal=cls.portal, papel=Membership.PAPEL_EDITOR,
        )
        Membership.objects.create(
            usuario=cls.admin_outro, portal=cls.outro, papel=Membership.PAPEL_ADMIN,
        )

    def _login_admin(self):
        self.client.force_login(self.admin)
        self.client.defaults.update(_host(self.portal.slug))

    def _url(self):
        return reverse('app_comecar')

    def test_admin_setup_pendente_get_200(self):
        self._login_admin()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Configure seu portal')
        self.assertContains(resp, 'O subdomínio não poderá ser alterado depois')
        self.assertContains(resp, 'Antes de começar, escolha o nome do seu portal')
        self.assertContains(resp, 'Criar meu portal')
        self.assertContains(resp, '.test')

    def test_nao_preenche_slug_provisorio_setup(self):
        self.portal.nome = 'Portal em configuração'
        self.portal.slug = 'setup-a1b2c3d4'
        self.portal.save(update_fields=['nome', 'slug'])
        self._login_admin()
        self.client.defaults.update(_host('setup-a1b2c3d4'))
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('value="Portal em configuração"', html)
        self.assertNotIn('value="setup-a1b2c3d4"', html)
        self.assertContains(resp, 'https://noticias-campinas.test')

    def test_get_setup_concluido_redireciona_dashboard(self):
        self.portal.setup_concluido = True
        self.portal.save(update_fields=['setup_concluido'])
        self._login_admin()
        resp = self.client.get(self._url())
        self.assertRedirects(resp, reverse('app_home'), fetch_redirect_response=False)

    def test_post_nome_vazio_falha(self):
        self._login_admin()
        resp = self.client.post(self._url(), {
            'nome': '   ',
            'slug': 'jornal-campinas',
        })
        self.assertEqual(resp.status_code, 200)
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertEqual(self.portal.slug, 'portal-provisorio-onb')
        self.assertTrue(resp.context['form'].errors['nome'])

    def test_post_slug_vazio_falha(self):
        self._login_admin()
        resp = self.client.post(self._url(), {
            'nome': 'Jornal de Campinas',
            'slug': '   ',
        })
        self.assertEqual(resp.status_code, 200)
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertTrue(resp.context['form'].errors['slug'])

    def test_post_slug_invalido_falha(self):
        self._login_admin()
        resp = self.client.post(self._url(), {
            'nome': 'Jornal de Campinas',
            'slug': '??? ***',
        })
        self.assertEqual(resp.status_code, 200)
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertTrue(resp.context['form'].errors['slug'])

    def test_post_slug_reservado_falha(self):
        self.assertIn('www', SLUGS_RESERVADOS)
        self._login_admin()
        for reservado in ('www', 'admin', 'app', 'plataforma', 'master'):
            resp = self.client.post(self._url(), {
                'nome': 'Jornal de Campinas',
                'slug': reservado,
            })
            self.assertEqual(resp.status_code, 200, reservado)
            self.assertTrue(resp.context['form'].errors['slug'], reservado)
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertEqual(self.portal.slug, 'portal-provisorio-onb')

    def test_post_slug_existente_nao_duplica(self):
        self._login_admin()
        resp = self.client.post(self._url(), {
            'nome': 'Jornal de Campinas',
            'slug': 'slug-ja-ocupado',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            'Este subdomínio já está em uso. Escolha outro.',
            resp.context['form'].errors['slug'][0],
        )
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertEqual(self.portal.slug, 'portal-provisorio-onb')
        self.assertEqual(Portal.objects.filter(slug='slug-ja-ocupado').count(), 1)

    def test_post_valido_salva_e_redireciona_novo_host(self):
        self._login_admin()
        resp = self.client.post(self._url(), {
            'nome': '  Jornal de Campinas  ',
            'slug': 'jornal-campinas',
        })
        self.assertEqual(resp.status_code, 302)
        self.portal.refresh_from_db()
        self.assertEqual(self.portal.nome, 'Jornal de Campinas')
        self.assertEqual(self.portal.slug, 'jornal-campinas')
        self.assertTrue(self.portal.setup_concluido)
        self.assertEqual(resp['Location'], 'http://jornal-campinas.test/app/')

    def test_apos_confirmacao_nao_reconfigura(self):
        self._login_admin()
        self.client.post(self._url(), {
            'nome': 'Jornal de Campinas',
            'slug': 'jornal-campinas',
        })
        self.client.defaults.update(_host('jornal-campinas'))
        resp_get = self.client.get(self._url())
        self.assertRedirects(resp_get, reverse('app_home'), fetch_redirect_response=False)
        resp_post = self.client.post(self._url(), {
            'nome': 'Outro nome',
            'slug': 'outro-slug-final',
        })
        self.assertRedirects(resp_post, reverse('app_home'), fetch_redirect_response=False)
        self.portal.refresh_from_db()
        self.assertEqual(self.portal.nome, 'Jornal de Campinas')
        self.assertEqual(self.portal.slug, 'jornal-campinas')
        self.assertTrue(self.portal.setup_concluido)

    def test_editor_nao_configura(self):
        self.client.force_login(self.editor)
        self.client.defaults.update(_host(self.portal.slug))
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 403)
        resp_post = self.client.post(self._url(), {
            'nome': 'Jornal de Campinas',
            'slug': 'jornal-campinas',
        })
        self.assertEqual(resp_post.status_code, 403)
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)

    def test_nao_configura_portal_de_outro_membership(self):
        self.client.force_login(self.admin)
        self.client.defaults.update(_host(self.outro.slug))
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 403)
        resp_post = self.client.post(self._url(), {
            'nome': 'Tentativa indevida',
            'slug': 'slug-indevido',
            'portal_id': self.outro.pk,
        })
        self.assertEqual(resp_post.status_code, 403)
        self.outro.refresh_from_db()
        self.assertFalse(self.outro.setup_concluido)
        self.assertEqual(self.outro.slug, 'outro-portal-onb')

    def test_slugify_acentos_e_espacos(self):
        form = PortalOnboardingForm(
            data={'nome': 'Jornal Campinas', 'slug': 'Jornal Campinas'},
            portal=self.portal,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['slug'], slugify('Jornal Campinas'))
        self.assertEqual(form.cleaned_data['slug'], 'jornal-campinas')
        form_acento = PortalOnboardingForm(
            data={'nome': 'Notícias São Paulo', 'slug': 'Notícias São Paulo'},
            portal=self.portal,
        )
        self.assertTrue(form_acento.is_valid(), form_acento.errors)
        self.assertEqual(form_acento.cleaned_data['slug'], 'noticias-sao-paulo')

    def test_preview_e_redirect_usam_tenant_base_domain(self):
        self._login_admin()
        resp = self.client.get(self._url())
        self.assertContains(resp, '.test')
        html = resp.content.decode()
        self.assertIn('https://portal-provisorio-onb.test', html)
        self.assertNotIn('portalnoticias.com.br', html)
        with override_settings(TENANT_BASE_DOMAIN='portalnoticias.com.br'):
            self.client.defaults.update(_host(self.portal.slug, base='portalnoticias.com.br'))
            resp_prod = self.client.get(self._url())
            self.assertContains(resp_prod, 'portalnoticias.com.br')
            resp_post = self.client.post(self._url(), {
                'nome': 'Jornal de Campinas',
                'slug': 'jornal-campinas',
            })
            self.assertEqual(
                resp_post['Location'],
                'http://jornal-campinas.portalnoticias.com.br/app/',
            )

    def test_integrity_error_slug_nao_gera_500(self):
        self._login_admin()
        with patch('plataforma.forms.slug_disponivel', return_value=True):
            resp = self.client.post(self._url(), {
                'nome': 'Jornal de Campinas',
                'slug': 'slug-ja-ocupado',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            'Este subdomínio acabou de ser ocupado. Escolha outro.',
            resp.context['form'].errors['slug'][0],
        )
        self.portal.refresh_from_db()
        self.assertFalse(self.portal.setup_concluido)
        self.assertEqual(self.portal.slug, 'portal-provisorio-onb')
        self.assertEqual(Portal.objects.filter(slug='slug-ja-ocupado').count(), 1)

    def test_aparencia_continua_sem_campo_slug(self):
        self.assertNotIn('slug', AparenciaForm.Meta.fields)
        self.portal.setup_concluido = True
        self.portal.save(update_fields=['setup_concluido'])
        self._login_admin()
        resp = self.client.get(reverse('app_aparencia'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="slug"')
        self.assertIsInstance(resp.context['form'], AparenciaForm)


class PortalOnboardingFormUnitTests(TestCase):
    def test_nao_aplica_sufixo_automatico(self):
        ocupado = Portal.objects.create(
            nome='Ocupado',
            slug='noticias-campinas',
            cidade='Campinas',
            estado='SP',
        )
        portal = Portal.objects.create(
            nome='Novo',
            slug='portal-novo-form',
            cidade='Campinas',
            estado='SP',
            setup_concluido=False,
        )
        form = PortalOnboardingForm(
            data={'nome': 'Notícias Campinas', 'slug': 'noticias-campinas'},
            portal=portal,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('já está em uso', form.errors['slug'][0])
        self.assertNotIn('noticias-campinas-2', str(form.cleaned_data) if form.is_valid() else '')
        ocupado.refresh_from_db()
        self.assertEqual(ocupado.slug, 'noticias-campinas')
