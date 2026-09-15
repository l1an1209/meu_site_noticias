"""Etapa 7.1: e-mail, recuperação, webhooks operacionais e Master."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from plataforma.models import AuditLog, Cliente, EmailLog, Plano, Portal, WebhookEvent
from plataforma.services.email import FAILED, NOT_CONFIGURED, SUCCESS, enviar_email, mascarar_email
from plataforma.services.kiwify import assinatura_kiwify
from plataforma.services.webhooks import payload_publico, processar_evento

User = get_user_model()
SECRET = 'kiwify-token-teste'


def _payload_aprovado(order_id='ord-ops-1', email='ops@cidade.test', sub_id='sub-ops-1'):
    body = {
        'order_id': order_id,
        'order_status': 'paid',
        'webhook_event_type': 'order_approved',
        'Product': {'product_id': 'prod-ops', 'product_name': 'Notícias Ops'},
        'Customer': {
            'full_name': 'Cliente Ops',
            'email': email,
            'mobile': '11999999999',
            'city': 'Campinas',
            'state': 'SP',
        },
        'Subscription': {
            'id': sub_id,
            'start_date': '2026-09-14T12:00:00Z',
            'next_payment': '2026-10-14T12:00:00Z',
            'status': 'active',
            'plan': {'id': 'plan-pro', 'name': 'Profissional'},
        },
        'signature': assinatura_kiwify(order_id, SECRET),
        'token': 'nao-deve-aparecer',
    }
    return body


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class EmailServicoTests(TestCase):
    def test_envio_sucesso(self):
        resultado = enviar_email('ok@test.com', 'Assunto', 'Corpo', tipo=EmailLog.TIPO_TESTE)
        self.assertEqual(resultado.status, SUCCESS)
        self.assertTrue(resultado.ok)
        self.assertEqual(len(mail.outbox), 1)
        log = EmailLog.objects.get(pk=resultado.log_id)
        self.assertEqual(log.status, EmailLog.STATUS_ENVIADO)
        self.assertNotIn('password', (log.erro or '').lower())

    def test_erro_smtp(self):
        with patch('plataforma.services.email.EmailMultiAlternatives.send', side_effect=OSError('SMTP down')):
            resultado = enviar_email('falha@test.com', 'Assunto', 'Corpo', tipo=EmailLog.TIPO_TESTE)
        self.assertEqual(resultado.status, FAILED)
        log = EmailLog.objects.get(pk=resultado.log_id)
        self.assertEqual(log.status, EmailLog.STATUS_FALHOU)
        self.assertIn('SMTP', log.erro)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend')
    def test_nao_configurado(self):
        resultado = enviar_email('x@test.com', 'Assunto', 'Corpo', tipo=EmailLog.TIPO_TESTE)
        self.assertEqual(resultado.status, NOT_CONFIGURED)
        self.assertEqual(EmailLog.objects.get(pk=resultado.log_id).status, EmailLog.STATUS_NAO_CONFIGURADO)

    def test_mascara_email(self):
        self.assertEqual(mascarar_email('luanpatrick@gmail.com'), 'lu***@gmail.com')


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class RecuperacaoSenhaTests(TestCase):
    def test_formulario_existe(self):
        resp = self.client.get(reverse('password_reset'), HTTP_HOST='localhost')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Esqueci a senha')

    def test_nao_enumera_email(self):
        User.objects.create_user('opsuser', 'existe@test.com', 'senha-forte-ops')
        inexistente = self.client.post(
            reverse('password_reset'), {'email': 'naoexiste@test.com'}, HTTP_HOST='localhost',
        )
        existente = self.client.post(
            reverse('password_reset'), {'email': 'existe@test.com'}, HTTP_HOST='localhost',
        )
        self.assertEqual(inexistente.status_code, 302)
        self.assertEqual(existente.status_code, 302)
        self.assertEqual(inexistente.url, existente.url)

    def test_envio_registrado_e_token_valido(self):
        user = User.objects.create_user('opsreset', 'reset@test.com', 'senha-forte-ops')
        resp = self.client.post(
            reverse('password_reset'), {'email': 'reset@test.com'}, HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EmailLog.objects.filter(
            tipo=EmailLog.TIPO_RECUPERACAO, destinatario='reset@test.com', status=EmailLog.STATUS_ENVIADO,
        ).exists())
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        confirm = self.client.get(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token}),
            HTTP_HOST='localhost',
        )
        self.assertIn(confirm.status_code, {200, 302})


@override_settings(
    ALLOWED_HOSTS=['*'],
    TENANT_COMPAT_FALLBACK=True,
    DEBUG=False,
    KIWIFY_WEBHOOK_SECRET=SECRET,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class MasterOperacaoTests(TestCase):
    def setUp(self):
        self.master = User.objects.create_superuser('ops-master', 'ops-master@test.com', 'senha-forte-ops')
        self.comum = User.objects.create_user('ops-comum', 'ops-comum@test.com', 'senha-forte-ops')

    def _login_master(self):
        self.client.force_login(self.master)
        return {'HTTP_HOST': 'localhost'}

    def _aprovar(self, **kwargs):
        payload = _payload_aprovado(**kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                reverse('webhook_kiwify'),
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_HOST='localhost',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        return payload

    def test_master_autorizado_e_nao_autorizado(self):
        host = {'HTTP_HOST': 'localhost'}
        self.assertEqual(self.client.get(reverse('master_saude'), **host).status_code, 302)
        self.client.force_login(self.comum)
        self.assertEqual(self.client.get(reverse('master_saude'), **host).status_code, 403)
        self.client.force_login(self.master)
        self.assertEqual(self.client.get(reverse('master_saude'), **host).status_code, 200)
        self.assertEqual(self.client.get(reverse('master_webhooks'), **host).status_code, 200)
        self.assertEqual(self.client.get(reverse('master_configuracoes'), **host).status_code, 200)
        self.assertEqual(self.client.get(reverse('master_busca'), **host).status_code, 200)
        self.assertEqual(self.client.get(reverse('master_auditoria'), **host).status_code, 200)

    def test_health_check_nao_envia_email(self):
        host = self._login_master()
        antes = EmailLog.objects.count()
        html = self.client.get(reverse('master_saude'), **host).content.decode()
        self.assertIn('Saúde do sistema', html)
        self.assertEqual(EmailLog.objects.count(), antes)

    def test_busca_e_auditoria(self):
        self._aprovar()
        host = self._login_master()
        html = self.client.get(reverse('master_busca') + '?q=ops@cidade', **host).content.decode()
        self.assertIn('ops@cidade.test', html)
        html2 = self.client.get(reverse('master_busca') + '?q=ord-ops-1', **host).content.decode()
        self.assertIn('ord-ops-1', html2)

    def test_reenvio_acesso_e_idor(self):
        self._aprovar()
        cliente = Cliente.objects.get(email='ops@cidade.test')
        host = {'HTTP_HOST': 'localhost'}
        self.client.force_login(self.comum)
        self.assertEqual(
            self.client.post(reverse('master_cliente_reenviar', args=[cliente.pk]), **host).status_code,
            403,
        )
        self.client.force_login(self.master)
        confirm = self.client.get(reverse('master_cliente_reenviar', args=[cliente.pk]), **host)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, 'Reenviar')
        resp = self.client.post(reverse('master_cliente_reenviar', args=[cliente.pk]), **host)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EmailLog.objects.filter(
            tipo=EmailLog.TIPO_REENVIO, destinatario='ops@cidade.test', status=EmailLog.STATUS_ENVIADO,
        ).exists())
        self.assertTrue(AuditLog.objects.filter(acao='reenvio_acesso', objeto_id=str(cliente.pk)).exists())
        corpo = mail.outbox[-1].body
        self.assertNotIn('senha-forte', corpo.lower())
        self.assertIn('/senha/redefinir/', corpo)

    def test_csrf_bloqueia_reenvio_sem_token(self):
        self._aprovar()
        cliente = Cliente.objects.get(email='ops@cidade.test')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.master)
        resp = csrf_client.post(
            reverse('master_cliente_reenviar', args=[cliente.pk]),
            HTTP_HOST='localhost',
        )
        self.assertEqual(resp.status_code, 403)

    def test_email_teste(self):
        host = self._login_master()
        resp = self.client.post(
            reverse('master_email_teste'),
            {'destino': 'teste-smtp@test.com'},
            **host,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EmailLog.objects.filter(
            tipo=EmailLog.TIPO_TESTE, destinatario='teste-smtp@test.com', status=EmailLog.STATUS_ENVIADO,
        ).exists())
        self.assertTrue(AuditLog.objects.filter(acao='email_teste').exists())

    def test_dashboard_problemas_e_timeline(self):
        self._aprovar()
        host = self._login_master()
        home = self.client.get(reverse('master_home'), **host)
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, 'Problemas que precisam de atenção')
        cliente = Cliente.objects.get(email='ops@cidade.test')
        detalhe = self.client.get(reverse('master_cliente', args=[cliente.pk]), **host)
        self.assertContains(detalhe, 'Cliente criado')
        self.assertContains(detalhe, 'Portal criado')
        self.assertContains(detalhe, 'Reenviar acesso')

    def test_webhook_falho_reprocessa_sem_duplicar(self):
        ruim = _payload_aprovado(order_id='ord-fail', email='', sub_id='sub-fail')
        ruim['Customer']['email'] = ''
        event = WebhookEvent.objects.create(
            provedor='kiwify',
            tipo='order_approved',
            id_externo='ord-fail',
            payload=ruim,
            status=WebhookEvent.STATUS_ERRO,
            processado=False,
        )
        resultado = processar_evento(event, payload=ruim)
        self.assertFalse(resultado['ok'])
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookEvent.STATUS_ERRO)

        bom = _payload_aprovado(order_id='ord-fail', email='recuperado@test.com', sub_id='sub-fail')
        event.payload = bom
        event.save(update_fields=['payload'])
        host = self._login_master()
        confirm = self.client.get(reverse('master_webhook_reprocessar', args=[event.pk]), **host)
        self.assertContains(confirm, 'Processar webhook novamente')
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse('master_webhook_reprocessar', args=[event.pk]), **host)
        self.assertEqual(resp.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookEvent.STATUS_PROCESSADO)
        self.assertEqual(Cliente.objects.filter(email='recuperado@test.com').count(), 1)
        self.assertEqual(Portal.objects.filter(cliente__email='recuperado@test.com').count(), 1)

        de_novo = self.client.post(reverse('master_webhook_reprocessar', args=[event.pk]), **host, follow=True)
        self.assertContains(de_novo, 'já foi processado')
        self.assertEqual(Cliente.objects.filter(email='recuperado@test.com').count(), 1)

    def test_payload_mascara_segredo(self):
        limpo = payload_publico({'order_id': 'x', 'signature': 'abc', 'token': 'zzz'})
        self.assertEqual(limpo['signature'], '***')
        self.assertEqual(limpo['token'], '***')
        self.assertEqual(limpo['order_id'], 'x')

    def test_onboarding_grava_email_log(self):
        self._aprovar()
        self.assertTrue(EmailLog.objects.filter(
            tipo=EmailLog.TIPO_ONBOARDING, destinatario='ops@cidade.test',
        ).exists())

    def test_isolamento_tenant_nas_rotas_novas(self):
        self._aprovar(email='a@iso.test', order_id='oa-iso', sub_id='sa-iso')
        self._aprovar(email='b@iso.test', order_id='ob-iso', sub_id='sb-iso')
        ua = User.objects.get(email='a@iso.test')
        pb = Portal.objects.get(cliente__email='b@iso.test')
        self.client.force_login(ua)
        self.assertEqual(
            self.client.get(reverse('master_cliente', args=[pb.cliente_id]), HTTP_HOST=f'{pb.slug}.test').status_code,
            403,
        )
        self.assertEqual(Plano.objects.filter(codigo='basico').count(), 1)
