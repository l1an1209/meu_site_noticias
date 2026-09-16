"""PWA por tenant: manifest, ícone e isolamento de host."""
from io import BytesIO
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from plataforma.models import Portal

_MEDIA = tempfile.mkdtemp(prefix='portal-pwa-')


def _png(rgb, name='marca.png'):
    buf = BytesIO()
    Image.new('RGB', (48, 48), rgb).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def _host(slug):
    return f'{slug}.test'


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    MEDIA_ROOT=_MEDIA,
    MEDIA_URL='/media/',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class PwaPorPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legado = Portal.objects.get(slug=Portal.SLUG_LEGADO)
        cls.beta = Portal.objects.get(slug=Portal.SLUG_TESTE)
        cls.legado.nome = 'Notícias Ji-Paraná'
        cls.legado.cidade = 'Ji-Paraná'
        cls.legado.cor_primaria = '#0d9488'
        cls.legado.logo.save('logo-a.png', _png((13, 148, 136), 'logo-a.png'), save=False)
        cls.legado.save()
        cls.beta.nome = 'Portal Beta Teste'
        cls.beta.cidade = 'Porto Velho'
        cls.beta.cor_primaria = '#ea580c'
        cls.beta.logo.save('logo-b.png', _png((234, 88, 12), 'logo-b.png'), save=False)
        cls.beta.save()

    def test_manifest_do_portal_a_nao_cita_portal_b(self):
        resp = self.client.get('/manifest.webmanifest', HTTP_HOST=_host(self.legado.slug))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['name'], 'Notícias Ji-Paraná')
        self.assertEqual(data['short_name'], 'Ji-Paraná')
        self.assertEqual(data['theme_color'], '#0d9488')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['start_url'], '/')
        self.assertNotIn('Portal Beta Teste', resp.content.decode())
        self.assertNotIn('Porto Velho', resp.content.decode())
        self.assertIn(_host(self.legado.slug), data['icons'][0]['src'])
        self.assertNotIn(_host(self.beta.slug), data['icons'][0]['src'])

    def test_manifest_do_portal_b_nao_cita_portal_a(self):
        resp = self.client.get('/manifest.webmanifest', HTTP_HOST=_host(self.beta.slug))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['name'], 'Portal Beta Teste')
        self.assertEqual(data['short_name'], 'Porto Velho')
        self.assertEqual(data['theme_color'], '#ea580c')
        self.assertNotIn('Notícias Ji-Paraná', resp.content.decode())
        self.assertNotIn('Ji-Paraná', data['short_name'])

    def test_host_plataforma_nao_tem_manifest(self):
        resp = self.client.get('/manifest.webmanifest', HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 404)

    def test_service_worker_so_no_tenant(self):
        resp = self.client.get('/sw.js', HTTP_HOST=_host(self.beta.slug))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/javascript', resp['Content-Type'])
        self.assertEqual(resp['Service-Worker-Allowed'], '/')
        self.assertIn('addEventListener', resp.content.decode())
        self.assertEqual(self.client.get('/sw.js', HTTP_HOST='localhost').status_code, 404)

    def test_icone_png_por_tenant(self):
        a = self.client.get('/pwa/icon/192.png', HTTP_HOST=_host(self.legado.slug))
        b = self.client.get('/pwa/icon/192.png', HTTP_HOST=_host(self.beta.slug))
        self.assertEqual(a.status_code, 200)
        self.assertEqual(b.status_code, 200)
        self.assertEqual(a['Content-Type'], 'image/png')
        self.assertNotEqual(a.content, b.content)
        self.assertEqual(self.client.get('/pwa/icon/64.png', HTTP_HOST=_host(self.beta.slug)).status_code, 404)

    def test_html_publico_aponta_manifest_e_site_segue_sem_pwa(self):
        html = self.client.get('/', HTTP_HOST=_host(self.beta.slug)).content.decode()
        self.assertIn('manifest.webmanifest', html)
        self.assertIn('serviceWorker', html)
        self.assertIn('Portal Beta Teste', html)
        landing = self.client.get('/', HTTP_HOST='localhost').content.decode()
        self.assertNotIn('manifest.webmanifest', landing)
        self.assertNotIn('serviceWorker.register', landing)
