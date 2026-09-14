"""Identidade pública 100% por portal (etapa 3)."""
from io import BytesIO
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from noticias.models import Categoria, Noticia
from plataforma.identity import identidade_do_portal, identidade_vazia
from plataforma.models import Portal

_MEDIA = tempfile.mkdtemp(prefix='portal-id3-')


def _png(rgb, name='marca.png'):
    buf = BytesIO()
    Image.new('RGB', (24, 24), rgb).save(buf, format='PNG')
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
class IdentidadePorPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legado = Portal.objects.get(slug=Portal.SLUG_LEGADO)
        cls.beta = Portal.objects.get(slug=Portal.SLUG_TESTE)
        cls.legado.logo.save('logo.png', _png((13, 148, 136), 'logo-a.png'), save=False)
        cls.legado.favicon.save('favicon.png', _png((26, 54, 93), 'fav-a.png'), save=False)
        cls.legado.save()
        cls.beta.logo.save('logo.png', _png((109, 40, 217), 'logo-b.png'), save=False)
        cls.beta.favicon.save('favicon.png', _png((245, 158, 11), 'fav-b.png'), save=False)
        cls.beta.save()

        cat = Categoria.all_objects.create(
            portal=cls.legado, nome='Cidade', slug='cidade-etapa3',
        )
        Noticia.all_objects.create(
            portal=cls.legado,
            categoria=cat,
            titulo='Conteudo legado etapa 3',
            conteudo='Matéria que deve continuar no portal de Ji-Paraná.',
        )
        cat_b = Categoria.all_objects.create(
            portal=cls.beta, nome='Geral', slug='geral-etapa3',
        )
        Noticia.all_objects.create(
            portal=cls.beta,
            categoria=cat_b,
            titulo='Materia exclusiva Beta',
            conteudo='Só o Portal Beta lista isto.',
        )

    def _get(self, slug, path='/'):
        return self.client.get(path, HTTP_HOST=_host(slug))

    def test_identidade_vazia_nao_cita_jiparana(self):
        data = identidade_vazia()
        blob = ' '.join(str(v) for v in data.values())
        self.assertNotIn('Ji-Paraná', blob)
        self.assertNotIn('Jiparaná', blob)
        self.assertNotIn('Rondônia', blob)

    def test_portal_a_mostra_somente_sua_identidade(self):
        resp = self._get(self.legado.slug)
        html = resp.content.decode()
        self.assertContains(resp, self.legado.nome)
        self.assertIn('Ji-Paraná', html)
        self.assertNotIn(self.beta.nome, html)
        self.assertNotIn('Campinas', html)
        self.assertNotIn('contato@portalbeta.test', html)
        self.assertIn(self.legado.cor_primaria, html)
        self.assertIn(self.legado.seo_description, html)

    def test_portal_b_mostra_somente_sua_identidade(self):
        resp = self._get(self.beta.slug)
        html = resp.content.decode()
        self.assertContains(resp, 'Portal Beta')
        self.assertContains(resp, 'Campinas')
        self.assertContains(resp, 'contato@portalbeta.test')
        self.assertContains(resp, 'Rodapé exclusivo do Portal Beta')
        self.assertContains(resp, self.beta.cor_primaria)
        self.assertNotIn('Ji-Paraná', html)
        self.assertNotIn('Jiparaná', html)
        self.assertNotIn('Rondônia', html)
        self.assertNotIn(self.legado.nome, html)
        self.assertNotIn('ca-pub-5451545777538942', html)

    def test_seo_meta_diferente_por_portal(self):
        html_a = self._get(self.legado.slug).content.decode()
        html_b = self._get(self.beta.slug).content.decode()
        self.assertIn(self.legado.seo_title, html_a)
        self.assertIn(self.beta.seo_title, html_b)
        self.assertNotIn(self.legado.seo_title, html_b)
        self.assertNotIn(self.beta.seo_title, html_a)
        self.assertIn(self.legado.seo_description, html_a)
        self.assertIn(self.beta.seo_description, html_b)
        self.assertIn(f'content="{self.legado.nome}"', html_a)
        self.assertIn(f'content="{self.beta.nome}"', html_b)

    def test_logo_e_favicon_diferentes(self):
        html_a = self._get(self.legado.slug).content.decode()
        html_b = self._get(self.beta.slug).content.decode()
        logo_a = self.legado.logo.url
        logo_b = self.beta.logo.url
        fav_a = self.legado.favicon.url
        fav_b = self.beta.favicon.url
        self.assertNotEqual(logo_a, logo_b)
        self.assertNotEqual(fav_a, fav_b)
        self.assertIn(logo_a, html_a)
        self.assertIn(logo_b, html_b)
        self.assertIn(fav_a, html_a)
        self.assertIn(fav_b, html_b)
        self.assertNotIn(logo_a, html_b)
        self.assertNotIn(logo_b, html_a)

    def test_rodape_e_contato_diferentes(self):
        html_a = self._get(self.legado.slug).content.decode()
        html_b = self._get(self.beta.slug).content.decode()
        self.assertIn(self.legado.texto_rodape, html_a)
        self.assertIn(self.beta.texto_rodape, html_b)
        self.assertIn('(19) 3333-0000', html_b)
        self.assertIn('wa.me/5511999000000', html_b)
        self.assertIn('facebook.com/portalbeta', html_b)
        self.assertNotIn('(19) 3333-0000', html_a)
        self.assertNotIn('wa.me/5511999000000', html_a)

    def test_legado_continua_listando_conteudo(self):
        resp = self._get(self.legado.slug)
        self.assertContains(resp, 'Conteudo legado etapa 3')
        self.assertNotContains(resp, 'Materia exclusiva Beta')
        resp_b = self._get(self.beta.slug)
        self.assertContains(resp_b, 'Materia exclusiva Beta')
        self.assertNotContains(resp_b, 'Conteudo legado etapa 3')

    def test_json_ld_usa_dados_do_portal(self):
        html_b = self._get(self.beta.slug).content.decode()
        self.assertIn('NewsMediaOrganization', html_b)
        self.assertIn('Campinas', html_b)
        self.assertIn('"addressRegion": "SP"', html_b)
        ctx = identidade_do_portal(self.beta)
        self.assertIn('Portal Beta', ctx['site_json_ld'])
        self.assertNotIn('Ji-Paraná', ctx['site_json_ld'])

    def test_adsense_so_no_legado(self):
        html_a = self._get(self.legado.slug).content.decode()
        self.assertIn('ca-pub-5451545777538942', html_a)

    def test_robots_sitemap_usa_host_do_tenant(self):
        resp = self.client.get('/robots.txt', HTTP_HOST=_host(self.beta.slug))
        self.assertIn(f'{self.beta.slug}.test/sitemap.xml', resp.content.decode())
