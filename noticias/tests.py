from django.db import IntegrityError
from django.test import TestCase

from noticias.models import Anuncio, Categoria, Noticia
from plataforma.models import Portal


class PortalScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legado = Portal.get_default()
        cls.outro = Portal.objects.create(
            nome='Notícias Cacoal',
            slug='noticiascacoal',
            cidade='Cacoal',
            estado='RO',
        )

    def test_categoria_sem_portal_usa_legado(self):
        cat = Categoria.objects.create(nome='Cidade Etapa1')
        self.assertEqual(cat.portal_id, self.legado.pk)

    def test_mesmo_slug_em_portais_diferentes(self):
        slug = 'policia-etapa1'
        Categoria.objects.create(portal=self.legado, nome='Polícia', slug=slug)
        Categoria.objects.create(portal=self.outro, nome='Polícia', slug=slug)
        self.assertEqual(Categoria.objects.filter(slug=slug).count(), 2)

    def test_slug_duplicado_no_mesmo_portal_falha(self):
        slug = 'policia-dup'
        Categoria.objects.create(portal=self.legado, nome='Polícia', slug=slug)
        with self.assertRaises(IntegrityError):
            Categoria.objects.create(portal=self.legado, nome='Polícia 2', slug=slug)

    def test_anuncio_mesmo_slot_em_portais_diferentes(self):
        Anuncio.objects.filter(slot='feed').delete()
        Anuncio.objects.create(portal=self.legado, slot='feed', titulo_interno='A')
        Anuncio.objects.create(portal=self.outro, slot='feed', titulo_interno='B')
        self.assertEqual(Anuncio.objects.filter(slot='feed').count(), 2)

    def test_noticia_herda_portal_padrao(self):
        noticia = Noticia.objects.create(titulo='Teste tenant', conteudo='Texto')
        self.assertEqual(noticia.portal_id, self.legado.pk)
