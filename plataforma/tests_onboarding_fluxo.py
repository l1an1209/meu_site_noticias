"""Auditoria Fase 6: fluxo SaaS ponta a ponta (webhook → e-mail → gate → slug → isolamento)."""
import inspect
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from noticias.models import Categoria, Noticia
from plataforma.models import Assinatura, Cliente, Membership, Portal
from plataforma.resolvers import resolve_portal_from_host
from plataforma.services.acesso import enviar_acesso
from plataforma.slugs import SLUGS_RESERVADOS, gerar_slug_provisorio
from plataforma.tests_comercial import SECRET, _payload_aprovado
from plataforma.tests_operacao import MockResendMixin, RESEND_TEST_KEY

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=['*'],
    SITE_URL='',
    TENANT_BASE_DOMAIN='portalnoticias.com.br',
    TENANT_COMPAT_FALLBACK=False,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESEND_API_KEY=RESEND_TEST_KEY,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class FluxoSaasIntegradoAuditoriaTests(MockResendMixin, TestCase):
    def _post_kiwify(self, payload):
        return self.client.post(
            reverse('webhook_kiwify'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='localhost',
        )

    def _host(self, slug):
        return {'HTTP_HOST': f'{slug}.portalnoticias.com.br'}

    def test_gerar_slug_provisorio_sem_dados_pessoais(self):
        fonte = inspect.getsource(gerar_slug_provisorio)
        self.assertIn('setup-', fonte)
        self.assertNotIn('email', fonte)
        self.assertNotIn('cidade', fonte)
        self.assertNotIn('product', fonte)
        slug = gerar_slug_provisorio()
        self.assertTrue(slug.startswith('setup-'))
        self.assertLessEqual(len(slug), 50)
        self.assertNotIn(slug, SLUGS_RESERVADOS)
        outro = gerar_slug_provisorio()
        self.assertNotEqual(slug, outro)

    def test_fluxo_completo_kiwify_onboarding_hostname_isolamento(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._post_kiwify(_payload_aprovado(
                order_id='ord-fluxo-1',
                email='fluxo@campinas.test',
                sub_id='sub-fluxo-1',
                product='Plano Básico',
            ))
        self.assertEqual(resp.status_code, 200, resp.content)

        cliente = Cliente.objects.get(email='fluxo@campinas.test')
        portal = Portal.objects.get(cliente=cliente)
        user = User.objects.get(email='fluxo@campinas.test')
        self.assertEqual(portal.nome, 'Portal em configuração')
        self.assertTrue(portal.slug.startswith('setup-'))
        self.assertNotEqual(portal.slug, 'plano-basico')
        self.assertIs(portal.setup_concluido, False)
        self.assertEqual(portal.plano.codigo, 'basico')
        self.assertEqual(Assinatura.objects.filter(portal=portal, status=Assinatura.STATUS_ATIVA).count(), 1)
        self.assertTrue(
            Membership.objects.filter(
                usuario=user, portal=portal, papel=Membership.PAPEL_ADMIN, ativo=True,
            ).exists()
        )
        self.assertEqual(resolve_portal_from_host(f'{portal.slug}.portalnoticias.com.br').pk, portal.pk)
        self.assertIsNone(resolve_portal_from_host('portal-inexistente.portalnoticias.com.br'))
        self.assertIsNone(resolve_portal_from_host('portalnoticias.com.br'))
        self.assertIsNone(resolve_portal_from_host('www.portalnoticias.com.br'))

        corpo = self.resend_payloads[-1]['text']
        self.assertEqual(self.resend_payloads[-1]['subject'], 'Seu acesso à plataforma foi criado')
        self.assertIn('configuração inicial', corpo.lower())
        self.assertIn('/entrar/', corpo)
        self.assertIn('/senha/redefinir/', corpo)
        self.assertNotIn(f'https://{portal.slug}.portalnoticias.com.br/', corpo)
        self.assertNotIn(f'{portal.slug}.portalnoticias.com.br', corpo)

        dup = self._post_kiwify(_payload_aprovado(
            order_id='ord-fluxo-1',
            email='fluxo@campinas.test',
            sub_id='sub-fluxo-1',
            product='Plano Básico',
        ))
        self.assertEqual(dup.status_code, 200)
        self.assertTrue(dup.json().get('duplicado'))
        self.assertEqual(Portal.objects.filter(cliente__email='fluxo@campinas.test').count(), 1)
        self.assertEqual(User.objects.filter(email='fluxo@campinas.test').count(), 1)
        self.assertEqual(Assinatura.objects.filter(kiwify_order_id='ord-fluxo-1').count(), 1)

        slug_provisorio = portal.slug
        user.set_password('senha-forte-f1')
        user.save(update_fields=['password'])
        login = self.client.post(
            reverse('entrar'),
            {'username': user.username, 'password': 'senha-forte-f1'},
            **self._host(slug_provisorio),
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login['Location'], reverse('app_home'))

        self.client.force_login(user)
        self.client.defaults.update(self._host(slug_provisorio))
        self.assertEqual(self.client.get(reverse('app_home'))['Location'], reverse('app_comecar'))
        self.assertEqual(self.client.get(reverse('app_noticias'))['Location'], reverse('app_comecar'))
        self.assertEqual(
            self.client.get(reverse('app_noticias'), {'next': reverse('app_aparencia')})['Location'],
            reverse('app_comecar'),
        )
        self.assertEqual(self.client.get(reverse('app_comecar')).status_code, 200)

        anon = self.client
        self.client.logout()
        resp_anon = self.client.post(
            reverse('app_comecar'),
            {'nome': 'Hack', 'slug': 'hack-slug', 'portal_id': portal.pk},
            **self._host(slug_provisorio),
        )
        self.assertEqual(resp_anon.status_code, 302)
        self.assertTrue(resp_anon['Location'].startswith(reverse('entrar')))
        portal.refresh_from_db()
        self.assertFalse(portal.setup_concluido)

        self.client.force_login(user)
        self.client.defaults.update(self._host(slug_provisorio))
        ocupado = Portal.objects.create(
            nome='Ocupado Fluxo',
            slug='noticias-campinas',
            cidade='Campinas',
            estado='SP',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        colisao = self.client.post(reverse('app_comecar'), {
            'nome': 'Notícias Campinas',
            'slug': 'noticias-campinas',
            'portal_id': ocupado.pk,
        })
        self.assertEqual(colisao.status_code, 200)
        self.assertIn('já está em uso', colisao.context['form'].errors['slug'][0])
        portal.refresh_from_db()
        self.assertEqual(portal.slug, slug_provisorio)

        for reservado in ('www', 'admin', 'plataforma', 'app', 'master'):
            r = self.client.post(reverse('app_comecar'), {
                'nome': 'Notícias Campinas', 'slug': reservado,
            })
            self.assertEqual(r.status_code, 200, reservado)

        ocupado.slug = 'noticias-campinas-ocupado'
        ocupado.save(update_fields=['slug'])
        ok = self.client.post(reverse('app_comecar'), {
            'nome': 'Notícias Campinas',
            'slug': 'noticias-campinas',
        })
        self.assertEqual(ok.status_code, 302)
        portal.refresh_from_db()
        self.assertEqual(portal.nome, 'Notícias Campinas')
        self.assertEqual(portal.slug, 'noticias-campinas')
        self.assertTrue(portal.setup_concluido)
        self.assertEqual(portal.host_previsto, 'noticias-campinas.portalnoticias.com.br')
        self.assertNotEqual(ok['Location'], f'https://{slug_provisorio}.portalnoticias.com.br/app/')
        self.assertEqual(
            ok['Location'],
            'http://noticias-campinas.portalnoticias.com.br/app/',
        )

        self.client.defaults.update(self._host('noticias-campinas'))
        self.assertEqual(self.client.get(reverse('app_home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('app_comecar')).status_code, 302)
        publico = self.client.get('/', **self._host('noticias-campinas'))
        self.assertEqual(publico.status_code, 200)

        outro = Portal.objects.create(
            nome='Notícias B',
            slug='noticias-b-fluxo',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
        )
        user_b = User.objects.create_user('fluxo_b', password='senha-forte-b1')
        Membership.objects.create(usuario=user_b, portal=outro, papel=Membership.PAPEL_ADMIN)
        cat_b = Categoria.all_objects.create(portal=outro, nome='Geral B', slug='geral-b-fluxo')
        Noticia.all_objects.create(
            portal=outro, categoria=cat_b, titulo='Segredo B Fluxo', conteudo='Só B',
        )
        self.client.force_login(user)
        self.client.defaults.update(self._host(outro.slug))
        self.assertEqual(self.client.get(reverse('app_home')).status_code, 403)
        self.assertEqual(self.client.get(reverse('app_comecar')).status_code, 403)
        self.assertNotContains(
            self.client.get('/', **self._host('noticias-campinas')),
            'Segredo B Fluxo',
        )

        payload_cfg = enviar_acesso(user, portal)
        self.assertTrue(payload_cfg.ok)
        corpo_cfg = self.resend_payloads[-1]['text']
        self.assertIn('https://noticias-campinas.portalnoticias.com.br/', corpo_cfg)
        self.assertNotIn('configuração inicial', corpo_cfg.lower())

        legado = Portal.objects.filter(slug='plano-basico').first()
        if legado is None:
            legado = Portal.objects.create(
                nome='Notícias',
                slug='plano-basico',
                cidade='Campinas',
                estado='SP',
                setup_concluido=True,
            )
        self.assertEqual(legado.slug, 'plano-basico')
        self.assertTrue(legado.setup_concluido)

        master = User.objects.create_superuser('fluxo_master', 'fm@test.com', 'senha-forte-m1')
        self.client.force_login(master)
        self.assertEqual(
            self.client.get(reverse('master_home'), HTTP_HOST='localhost').status_code,
            200,
        )
        self.client.defaults.update(self._host(slug_provisorio))
        self.assertEqual(self.client.get(reverse('app_home'), **self._host('noticias-campinas')).status_code, 200)
