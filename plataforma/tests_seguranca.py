"""Etapa 5: autenticação, IDOR, uploads, sitemap, erros e isolamento extra."""
import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from noticias.image_utils import FORBIDDEN_EXTS, tenant_media_path, validate_image_file, validate_video_file
from noticias.models import Categoria, Contribuicao, Noticia
from plataforma.forms import NoticiaForm
from plataforma.models import AuditLog, Membership, Portal
from plataforma.security import log_audit

User = get_user_model()


def _host(slug):
    return f'{slug}.test'


def _jpeg(name='foto.jpg'):
    buf = BytesIO()
    Image.new('RGB', (12, 12), color=(200, 30, 30)).save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SegurancaIsolamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.portal_a = Portal.objects.create(
            nome='Portal Alfa Seg',
            slug='seg-alfa',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
        )
        cls.portal_b = Portal.objects.create(
            nome='Portal Beta Seg',
            slug='seg-beta',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
        )
        cls.cat_a = Categoria.all_objects.create(
            portal=cls.portal_a, nome='Geral', slug='geral-seg-a',
        )
        cls.cat_b = Categoria.all_objects.create(
            portal=cls.portal_b, nome='Geral', slug='geral-seg-b',
        )
        cls.noticia_a = Noticia.all_objects.create(
            portal=cls.portal_a,
            categoria=cls.cat_a,
            titulo='Titulo secreto Alfa XYZ',
            conteudo='Corpo A',
        )
        cls.noticia_b = Noticia.all_objects.create(
            portal=cls.portal_b,
            categoria=cls.cat_b,
            titulo='Titulo secreto Beta XYZ',
            conteudo='Corpo B',
        )
        cls.envio_b = Contribuicao.all_objects.create(
            portal=cls.portal_b,
            titulo='Envio secreto Beta',
            conteudo='Texto B',
            nome='Morador B',
            email='b@test.com',
            status='pendente',
        )
        cls.admin_a = User.objects.create_user('seg_admin_a', password='senha-forte-a1')
        cls.admin_b = User.objects.create_user('seg_admin_b', password='senha-forte-b1')
        cls.autor_a = User.objects.create_user('seg_autor_a', password='senha-forte-r1')
        cls.autor_a2 = User.objects.create_user('seg_autor_a2', password='senha-forte-r2')
        cls.comum = User.objects.create_user('seg_comum', password='senha-forte-c1')
        cls.master = User.objects.create_superuser('seg_master', 'segm@test.com', 'senha-forte-m1')
        Membership.objects.create(
            usuario=cls.admin_a, portal=cls.portal_a, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.admin_b, portal=cls.portal_b, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.autor_a, portal=cls.portal_a, papel=Membership.PAPEL_AUTOR,
        )
        Membership.objects.create(
            usuario=cls.autor_a2, portal=cls.portal_a, papel=Membership.PAPEL_AUTOR,
        )
        cls.noticia_autor = Noticia.all_objects.create(
            portal=cls.portal_a,
            categoria=cls.cat_a,
            titulo='Do autor A',
            conteudo='Texto',
            criado_por=cls.autor_a,
        )
        cls.noticia_autor2 = Noticia.all_objects.create(
            portal=cls.portal_a,
            categoria=cls.cat_a,
            titulo='Do outro autor',
            conteudo='Texto',
            criado_por=cls.autor_a2,
        )

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _client(self, slug, user=None):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        self.client.defaults['HTTP_HOST'] = _host(slug)
        return self.client

    def test_idor_noticia_de_outro_portal_retorna_404(self):
        c = self._client(self.portal_a.slug)
        resp = c.get(reverse('detalhe', args=[self.noticia_b.pk]))
        self.assertEqual(resp.status_code, 404)
        body = resp.content.decode()
        self.assertNotIn(self.noticia_b.titulo, body)
        self.assertNotIn('Corpo B', body)

    def test_idor_editar_noticia_de_outro_portal_retorna_404(self):
        c = self._client(self.portal_a.slug, self.admin_a)
        url = reverse('app_noticia_editar', args=[self.noticia_b.pk])
        resp = c.get(url)
        self.assertEqual(resp.status_code, 404)
        resp_post = c.post(url, {
            'titulo': 'Hackeado',
            'conteudo': 'x',
            'resumo': '',
            'autor': 'x',
            'categoria': self.cat_a.pk,
        })
        self.assertEqual(resp_post.status_code, 404)
        self.noticia_b.refresh_from_db()
        self.assertEqual(self.noticia_b.titulo, 'Titulo secreto Beta XYZ')

    def test_idor_envio_de_outro_portal_nao_aprova(self):
        c = self._client(self.portal_a.slug, self.admin_a)
        resp = c.post(reverse('app_aprovar_envio', args=[self.envio_b.pk]))
        self.assertEqual(resp.status_code, 404)
        self.envio_b.refresh_from_db()
        self.assertEqual(self.envio_b.status, 'pendente')

    def test_app_de_outro_portal_e_403(self):
        c = self._client(self.portal_b.slug, self.admin_a)
        resp = c.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn(self.noticia_b.titulo, resp.content.decode())

    def test_usuario_comum_nao_acessa_master(self):
        c = self._client(self.portal_a.slug, self.comum)
        resp = c.get(reverse('master_home'))
        self.assertEqual(resp.status_code, 403)

    def test_admin_do_portal_nao_acessa_master(self):
        c = self._client(self.portal_a.slug, self.admin_a)
        resp = c.get(reverse('master_home'))
        self.assertEqual(resp.status_code, 403)

    def test_autor_nao_edita_noticia_de_outro_autor(self):
        c = self._client(self.portal_a.slug, self.autor_a)
        resp = c.get(reverse('app_noticia_editar', args=[self.noticia_autor2.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_form_rejeita_categoria_de_outro_portal(self):
        form = NoticiaForm(
            data={
                'titulo': 'Cruzado',
                'conteudo': 'Texto',
                'resumo': '',
                'autor': 'Redação',
                'categoria': self.cat_b.pk,
            },
            portal=self.portal_a,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('categoria', form.errors)

    def test_sitemap_nao_lista_conteudo_do_outro_portal(self):
        c = self._client(self.portal_a.slug)
        resp = c.get('/sitemap.xml')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f'/noticia/{self.noticia_a.pk}/', body)
        self.assertNotIn(f'/noticia/{self.noticia_b.pk}/', body)
        self.assertNotIn('Titulo secreto Beta XYZ', body)

    def test_robots_bloqueia_paineis(self):
        c = self._client(self.portal_a.slug)
        body = c.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /app/', body)
        self.assertIn('Disallow: /master/', body)

    def test_pagina_404_nao_vaza_interno(self):
        c = self._client(self.portal_a.slug)
        resp = c.get('/pagina-inexistente-etapa5/')
        self.assertEqual(resp.status_code, 404)
        body = resp.content.decode()
        self.assertNotIn('Traceback', body)
        self.assertNotIn('C:\\', body)
        self.assertNotIn('SECRET_KEY', body)
        self.assertIn(self.portal_a.nome, body)

    def test_recuperacao_de_senha_existe(self):
        c = self._client(self.portal_a.slug)
        resp = c.get(reverse('password_reset'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Esqueci a senha')

    def test_login_invalido_nao_entra(self):
        c = self._client(self.portal_a.slug)
        resp = c.post(reverse('entrar'), {'username': 'seg_admin_a', 'password': 'errada'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_login_throttle(self):
        c = self._client(self.portal_a.slug)
        with override_settings(LOGIN_THROTTLE_LIMIT=3, LOGIN_THROTTLE_WINDOW=60):
            for _ in range(3):
                c.post(reverse('entrar'), {'username': 'nobody', 'password': 'x'})
            resp = c.post(reverse('entrar'), {'username': 'nobody', 'password': 'x'})
            self.assertEqual(resp.status_code, 429)

    def test_open_redirect_aprovacao_ignorado(self):
        envio = Contribuicao.all_objects.create(
            portal=self.portal_a,
            titulo='Envio Alfa',
            conteudo='Texto',
            nome='A',
            email='a@test.com',
            status='pendente',
        )
        c = self._client(self.portal_a.slug, self.admin_a)
        resp = c.post(
            reverse('app_aprovar_envio', args=[envio.pk]),
            {'next': 'https://evil.example/phish'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp['Location'])

    def test_auditoria_nao_grava_senha(self):
        req = RequestFactory().get('/')
        req.user = self.admin_a
        req.portal = self.portal_a
        log_audit(req, 'teste', detalhes={'password': 'secreto', 'ok': 1})
        last = AuditLog.objects.order_by('-id').first()
        self.assertIsNotNone(last)
        self.assertNotIn('password', last.detalhes)
        self.assertEqual(last.detalhes.get('ok'), 1)


class UploadsSegurosTests(TestCase):
    def test_rejeita_executavel_como_imagem(self):
        uploaded = SimpleUploadedFile(
            'shell.php',
            b'<?php echo 1;',
            content_type='application/x-php',
        )
        with self.assertRaises(Exception):
            validate_image_file(uploaded)

    def test_rejeita_svg(self):
        uploaded = SimpleUploadedFile(
            'x.svg',
            b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            content_type='image/svg+xml',
        )
        with self.assertRaises(Exception):
            validate_image_file(uploaded)

    def test_php_esta_na_lista_proibida(self):
        self.assertIn('.php', FORBIDDEN_EXTS)
        self.assertIn('.exe', FORBIDDEN_EXTS)
        self.assertIn('.svg', FORBIDDEN_EXTS)

    def test_caminho_de_midia_usa_slug_do_tenant(self):
        portal = Portal(slug='meu-portal')
        noticia = Noticia(portal=portal)
        path = tenant_media_path(noticia, '../../etc/passwd.jpg', 'noticias', {'.jpg'}, '.jpg')
        self.assertTrue(path.startswith('portais/meu-portal/noticias/'))
        self.assertNotIn('..', path)
        self.assertTrue(path.endswith('.jpg'))

    def test_video_php_rejeitado(self):
        uploaded = SimpleUploadedFile('video.php.mp4', b'<?php', content_type='video/mp4')
        uploaded.name = 'malware.php'
        with self.assertRaises(Exception):
            validate_video_file(uploaded)


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
)
class UploadHttpTenantTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_upload_imagem_fica_na_pasta_do_portal(self):
        portal = Portal.objects.create(
            nome='Upl A', slug='upl-a', cidade='X', estado='RO', status=Portal.STATUS_ATIVO,
        )
        cat = Categoria.all_objects.create(portal=portal, nome='G', slug='g-upl')
        user = User.objects.create_user('upl_admin', password='senha-forte-u1')
        Membership.objects.create(usuario=user, portal=portal, papel=Membership.PAPEL_ADMIN)
        with override_settings(MEDIA_ROOT=self.tmp.name):
            self.client.force_login(user)
            self.client.defaults['HTTP_HOST'] = _host(portal.slug)
            resp = self.client.post(
                reverse('app_noticia_nova'),
                {
                    'titulo': 'Com foto',
                    'conteudo': 'Texto da noticia',
                    'resumo': '',
                    'autor': 'Redação',
                    'categoria': cat.pk,
                    'imagem': _jpeg(),
                },
            )
            self.assertEqual(resp.status_code, 302)
            noticia = Noticia.all_objects.get(titulo='Com foto')
            self.assertTrue(noticia.imagem.name.startswith(f'portais/{portal.slug}/noticias/'))
            self.assertTrue(Path(self.tmp.name, noticia.imagem.name).exists())

    def test_upload_php_pelo_painel_e_rejeitado(self):
        portal = Portal.objects.create(
            nome='Upl B', slug='upl-b', cidade='X', estado='RO', status=Portal.STATUS_ATIVO,
        )
        cat = Categoria.all_objects.create(portal=portal, nome='G', slug='g-upl-b')
        user = User.objects.create_user('upl_admin2', password='senha-forte-u2')
        Membership.objects.create(usuario=user, portal=portal, papel=Membership.PAPEL_ADMIN)
        with override_settings(MEDIA_ROOT=self.tmp.name):
            self.client.force_login(user)
            self.client.defaults['HTTP_HOST'] = _host(portal.slug)
            evil = SimpleUploadedFile('shell.php', b'<?php echo 1;', content_type='application/x-php')
            resp = self.client.post(
                reverse('app_noticia_nova'),
                {
                    'titulo': 'Ataque',
                    'conteudo': 'Texto',
                    'resumo': '',
                    'autor': 'Redação',
                    'categoria': cat.pk,
                    'imagem': evil,
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(Noticia.all_objects.filter(titulo='Ataque').exists())
            saved = list(Path(self.tmp.name).rglob('*.php'))
            self.assertEqual(saved, [])
