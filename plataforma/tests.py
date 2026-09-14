from django.contrib.auth import get_user_model
from django.test import TestCase

from plataforma.models import Membership, Plano, Portal


User = get_user_model()


class PortalModelTests(TestCase):
    def test_get_default_usa_slug_legado(self):
        legado = Portal.get_default()
        self.assertIsNotNone(legado)
        self.assertEqual(legado.slug, Portal.SLUG_LEGADO)
        outro = Portal.objects.create(
            nome='Cacoal',
            slug='noticiascacoal',
            cidade='Cacoal',
            estado='RO',
        )
        self.assertEqual(Portal.get_default().pk, legado.pk)
        self.assertNotEqual(Portal.get_default().pk, outro.pk)

    def test_membership_unico_por_usuario_e_portal(self):
        portal = Portal.get_default()
        user = User.objects.create_user('editor', password='x')
        Membership.objects.create(
            usuario=user,
            portal=portal,
            papel=Membership.PAPEL_EDITOR,
        )
        with self.assertRaises(Exception):
            Membership.objects.create(
                usuario=user,
                portal=portal,
                papel=Membership.PAPEL_ADMIN,
            )
