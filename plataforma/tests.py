from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings

from plataforma.models import Membership, Portal
from plataforma.resolvers import resolve_portal_from_host


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


class PortalSetupConcluidoTests(TestCase):
    def test_novo_portal_nasce_com_setup_false(self):
        portal = Portal.objects.create(
            nome='Portal novo setup',
            slug='portal-novo-setup',
            cidade='Cacoal',
            estado='RO',
        )
        self.assertIs(portal.setup_concluido, False)
        self.assertIs(
            Portal.objects.get(pk=portal.pk).setup_concluido,
            False,
        )

    def test_portais_seed_da_migration_ficam_com_setup_true(self):
        for slug in (Portal.SLUG_LEGADO, Portal.SLUG_TESTE):
            portal = Portal.objects.get(slug=slug)
            self.assertIs(portal.setup_concluido, True, slug)

    def test_setup_concluido_aceita_true_e_false(self):
        portal = Portal.objects.create(
            nome='Portal toggle setup',
            slug='portal-toggle-setup',
            cidade='Vilhena',
            estado='RO',
        )
        self.assertIs(portal.setup_concluido, False)
        portal.setup_concluido = True
        portal.save(update_fields=['setup_concluido'])
        portal.refresh_from_db()
        self.assertIs(portal.setup_concluido, True)
        portal.setup_concluido = False
        portal.save(update_fields=['setup_concluido'])
        portal.refresh_from_db()
        self.assertIs(portal.setup_concluido, False)

    def test_slug_unico_continua_valendo(self):
        Portal.objects.create(
            nome='Slug A',
            slug='slug-unico-setup',
            cidade='Ariquemes',
            estado='RO',
        )
        with self.assertRaises(IntegrityError):
            Portal.objects.create(
                nome='Slug B',
                slug='slug-unico-setup',
                cidade='Ariquemes',
                estado='RO',
            )

    @override_settings(ALLOWED_HOSTS=['*'], TENANT_COMPAT_FALLBACK=False)
    def test_plano_basico_slug_inalterado_e_resolve_host(self):
        existente = Portal.objects.filter(slug='plano-basico').first()
        if existente is None:
            portal = Portal.objects.create(
                nome='Notícias',
                slug='plano-basico',
                cidade='Campinas',
                estado='SP',
                setup_concluido=True,
            )
        else:
            portal = existente
            self.assertIs(portal.setup_concluido, True)
        self.assertEqual(portal.slug, 'plano-basico')
        resolved = resolve_portal_from_host('plano-basico.portalnoticias.com.br')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, portal.pk)
        self.assertEqual(resolved.slug, 'plano-basico')
