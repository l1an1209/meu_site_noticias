from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from plataforma.models import Cliente, ConversaAjuda, Membership, MensagemAjuda, Portal

User = get_user_model()


def _host(slug):
    return {'HTTP_HOST': f'{slug}.test'}


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class CentralAjudaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente_a = Cliente.objects.create(nome='Cliente Alfa', email='alfa@test.com')
        cls.cliente_b = Cliente.objects.create(nome='Cliente Beta', email='beta@test.com')
        cls.portal_a = Portal.objects.create(
            nome='Portal Alfa',
            slug='portala',
            cidade='Cacoal',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
            cliente=cls.cliente_a,
            cliente_email='alfa@test.com',
            cliente_nome='Cliente Alfa',
        )
        cls.portal_b = Portal.objects.create(
            nome='Portal Beta',
            slug='portalb',
            cidade='Vilhena',
            estado='RO',
            status=Portal.STATUS_ATIVO,
            setup_concluido=True,
            cliente=cls.cliente_b,
            cliente_email='beta@test.com',
            cliente_nome='Cliente Beta',
        )
        cls.admin_a = User.objects.create_user('admin_a', password='pass-a')
        cls.editor_a = User.objects.create_user('editor_a', password='pass-e')
        cls.admin_b = User.objects.create_user('admin_b', password='pass-b')
        cls.leitor = User.objects.create_user('leitor', password='pass-l')
        cls.master = User.objects.create_superuser('master', 'master@test.com', 'pass-master')
        Membership.objects.create(
            usuario=cls.admin_a, portal=cls.portal_a, papel=Membership.PAPEL_ADMIN,
        )
        Membership.objects.create(
            usuario=cls.editor_a, portal=cls.portal_a, papel=Membership.PAPEL_EDITOR,
        )
        Membership.objects.create(
            usuario=cls.admin_b, portal=cls.portal_b, papel=Membership.PAPEL_ADMIN,
        )

    def _login(self, user, slug):
        self.client.force_login(user)
        return _host(slug)

    def test_membro_abre_conversa_e_envia_mensagem(self):
        host = self._login(self.admin_a, 'portala')
        resp = self.client.get(reverse('app_ajuda'), **host)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nova conversa')
        self.assertContains(resp, 'Ajuda')
        criar = self.client.post(reverse('app_ajuda'), {
            'tipo': ConversaAjuda.TIPO_PROBLEMA,
            'assunto': 'Não consigo publicar',
            'texto': 'O botão de salvar não responde.',
        }, **host)
        self.assertEqual(criar.status_code, 302)
        conversa = ConversaAjuda.all_objects.get(portal=self.portal_a)
        self.assertEqual(conversa.tipo, ConversaAjuda.TIPO_PROBLEMA)
        self.assertEqual(conversa.aberto_por, self.admin_a)
        self.assertEqual(conversa.mensagens.count(), 1)
        self.assertEqual(conversa.status, ConversaAjuda.STATUS_AGUARDANDO_SUPORTE)
        self.assertRedirects(criar, reverse('app_ajuda_conversa', args=[conversa.pk]))

    def test_editor_ve_conversa_aberta_pelo_admin_do_mesmo_portal(self):
        conversa = ConversaAjuda.all_objects.create(
            portal=self.portal_a,
            aberto_por=self.admin_a,
            tipo=ConversaAjuda.TIPO_DUVIDA,
            assunto='Dúvida do admin',
        )
        conversa.adicionar_mensagem(self.admin_a, MensagemAjuda.ORIGEM_CLIENTE, 'Primeira')
        host = self._login(self.editor_a, 'portala')
        lista = self.client.get(reverse('app_ajuda'), **host)
        self.assertContains(lista, 'Dúvida do admin')
        detalhe = self.client.get(reverse('app_ajuda_conversa', args=[conversa.pk]), **host)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, 'Primeira')
        envio = self.client.post(
            reverse('app_ajuda_conversa', args=[conversa.pk]),
            {'texto': 'Continuando pela editora'},
            **host,
        )
        self.assertEqual(envio.status_code, 302)
        self.assertTrue(
            conversa.mensagens.filter(texto='Continuando pela editora').exists()
        )

    def test_master_recebe_mensagem_e_responde(self):
        conversa = ConversaAjuda.all_objects.create(
            portal=self.portal_a,
            aberto_por=self.admin_a,
            assunto='Ajuda com fotos',
            tipo=ConversaAjuda.TIPO_DUVIDA,
        )
        conversa.adicionar_mensagem(self.admin_a, MensagemAjuda.ORIGEM_CLIENTE, 'Como envio fotos?')
        self.client.force_login(self.master)
        host = {'HTTP_HOST': 'localhost'}
        lista = self.client.get(reverse('master_atendimento'), **host)
        self.assertEqual(lista.status_code, 200)
        self.assertContains(lista, 'Ajuda com fotos')
        self.assertContains(lista, 'Portal Alfa')
        self.assertContains(lista, 'alfa@test.com')
        detalhe = self.client.get(
            reverse('master_atendimento_conversa', args=[conversa.pk]), **host,
        )
        self.assertContains(detalhe, 'Como envio fotos?')
        resp = self.client.post(
            reverse('master_atendimento_conversa', args=[conversa.pk]),
            {'acao': 'responder', 'texto': 'Vou te ajudar. Faça isso...'},
            **host,
        )
        self.assertEqual(resp.status_code, 302)
        conversa.refresh_from_db()
        self.assertEqual(conversa.status, ConversaAjuda.STATUS_AGUARDANDO_CLIENTE)
        self.assertTrue(conversa.mensagens.filter(origem=MensagemAjuda.ORIGEM_SUPORTE).exists())

        host_a = self._login(self.admin_a, 'portala')
        poll = self.client.get(
            reverse('app_ajuda_poll', args=[conversa.pk]) + '?depois=0',
            **host_a,
        )
        self.assertEqual(poll.status_code, 200)
        dados = poll.json()
        textos = [m['texto'] for m in dados['mensagens']]
        self.assertIn('Vou te ajudar. Faça isso...', textos)

    def test_polling_retorna_somente_mensagens_novas(self):
        conversa = ConversaAjuda.all_objects.create(
            portal=self.portal_a, aberto_por=self.admin_a, assunto='Poll',
        )
        primeira = conversa.adicionar_mensagem(
            self.admin_a, MensagemAjuda.ORIGEM_CLIENTE, 'Oi',
        )
        host = self._login(self.admin_a, 'portala')
        vazio = self.client.get(
            reverse('app_ajuda_poll', args=[conversa.pk]) + f'?depois={primeira.pk}',
            **host,
        )
        self.assertEqual(vazio.json()['mensagens'], [])
        segunda = conversa.adicionar_mensagem(
            self.master, MensagemAjuda.ORIGEM_SUPORTE, 'Resposta nova',
        )
        novo = self.client.get(
            reverse('app_ajuda_poll', args=[conversa.pk]) + f'?depois={primeira.pk}',
            **host,
        )
        ids = [m['id'] for m in novo.json()['mensagens']]
        self.assertEqual(ids, [segunda.pk])

    def test_cliente_nao_ve_conversa_de_outro_portal(self):
        conversa_b = ConversaAjuda.all_objects.create(
            portal=self.portal_b,
            aberto_por=self.admin_b,
            assunto='Segredo Beta Ajuda',
        )
        conversa_b.adicionar_mensagem(self.admin_b, MensagemAjuda.ORIGEM_CLIENTE, 'Só do B')
        host = self._login(self.admin_a, 'portala')
        lista = self.client.get(reverse('app_ajuda'), **host)
        self.assertNotContains(lista, 'Segredo Beta Ajuda')
        self.assertEqual(
            self.client.get(reverse('app_ajuda_conversa', args=[conversa_b.pk]), **host).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('app_ajuda_poll', args=[conversa_b.pk]), **host).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('app_ajuda_conversa', args=[conversa_b.pk]),
                {'texto': 'tentativa'},
                **host,
            ).status_code,
            404,
        )
        self.assertFalse(
            conversa_b.mensagens.filter(texto='tentativa').exists()
        )

    def test_membro_do_portal_b_nao_acessa_ajuda_no_host_a(self):
        conversa_a = ConversaAjuda.all_objects.create(
            portal=self.portal_a, aberto_por=self.admin_a, assunto='Só Alfa',
        )
        host = self._login(self.admin_b, 'portala')
        resp = self.client.get(reverse('app_ajuda'), **host)
        self.assertNotEqual(resp.status_code, 200)
        self.assertEqual(
            self.client.get(reverse('app_ajuda_conversa', args=[conversa_a.pk]), **host).status_code,
            403,
        )

    def test_encerrar_e_reabrir(self):
        conversa = ConversaAjuda.all_objects.create(
            portal=self.portal_a, aberto_por=self.admin_a, assunto='Encerrar',
        )
        conversa.adicionar_mensagem(self.admin_a, MensagemAjuda.ORIGEM_CLIENTE, 'Oi')
        self.client.force_login(self.master)
        host = {'HTTP_HOST': 'localhost'}
        self.client.post(
            reverse('master_atendimento_conversa', args=[conversa.pk]),
            {'acao': 'status', 'status': ConversaAjuda.STATUS_ENCERRADA},
            **host,
        )
        conversa.refresh_from_db()
        self.assertEqual(conversa.status, ConversaAjuda.STATUS_ENCERRADA)
        self.assertIsNotNone(conversa.encerrado_em)
        self.client.post(
            reverse('master_atendimento_conversa', args=[conversa.pk]),
            {'acao': 'status', 'status': ConversaAjuda.STATUS_AGUARDANDO_SUPORTE},
            **host,
        )
        conversa.refresh_from_db()
        self.assertEqual(conversa.status, ConversaAjuda.STATUS_AGUARDANDO_SUPORTE)
        self.assertIsNone(conversa.encerrado_em)
        self.client.post(
            reverse('master_atendimento_conversa', args=[conversa.pk]),
            {'acao': 'status', 'status': ConversaAjuda.STATUS_ENCERRADA},
            **host,
        )
        host_a = self._login(self.admin_a, 'portala')
        self.client.post(
            reverse('app_ajuda_conversa', args=[conversa.pk]),
            {'texto': 'Reabrindo pelo cliente'},
            **host_a,
        )
        conversa.refresh_from_db()
        self.assertEqual(conversa.status, ConversaAjuda.STATUS_AGUARDANDO_SUPORTE)

    def test_anonimo_e_leitor_sem_membership_nao_entram(self):
        resp = self.client.get(reverse('app_ajuda'), HTTP_HOST='portala.test')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp['Location'].startswith(reverse('entrar')))
        self.client.force_login(self.leitor)
        resp2 = self.client.get(reverse('app_ajuda'), HTTP_HOST='portala.test')
        self.assertNotEqual(resp2.status_code, 200)
        comum = self.client.get(reverse('master_atendimento'), HTTP_HOST='localhost')
        self.assertIn(comum.status_code, (302, 403))

    def test_nao_membro_nao_acessa_master_atendimento(self):
        self.client.force_login(self.admin_a)
        resp = self.client.get(reverse('master_atendimento'), HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 403)

    def test_jornal_publico_nao_tem_ajuda(self):
        resp = self.client.get('/', HTTP_HOST='portala.test')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('/app/ajuda/', html)
        self.assertNotIn('Central de Ajuda', html)
        self.assertNotIn(reverse('app_ajuda'), html)
        self.assertEqual(self.client.get('/ajuda/', HTTP_HOST='portala.test').status_code, 404)
        self.assertEqual(
            self.client.get(reverse('app_ajuda'), HTTP_HOST='portala.test').status_code,
            302,
        )

    def test_envio_json_ajax(self):
        conversa = ConversaAjuda.all_objects.create(
            portal=self.portal_a, aberto_por=self.admin_a, assunto='Ajax',
        )
        host = self._login(self.admin_a, 'portala')
        resp = self.client.post(
            reverse('app_ajuda_conversa', args=[conversa.pk]),
            {'texto': 'Mensagem ajax'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            **host,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(resp.json()['mensagem']['texto'], 'Mensagem ajax')
