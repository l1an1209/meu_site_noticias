import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from plataforma.models import Assinatura, AuditLog, Cliente, EmailLog, Portal, WebhookEvent
from plataforma.security import log_audit
from plataforma.services.acesso import enviar_acesso, usuario_do_cliente
from plataforma.services.email import diagnosticar_smtp, enviar_email, mascarar_email
from plataforma.services.saude import verificar_saude
from plataforma.services.webhooks import payload_publico, processar_evento
from plataforma.views_master import MasterRequiredMixin

User = get_user_model()


class MasterSaudeView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/saude.html'
    app_active = 'saude'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['checks'] = verificar_saude()
        return ctx


class MasterConfiguracoesView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/configuracoes.html'
    app_active = 'config'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['smtp'] = diagnosticar_smtp(conectar=False)
        ctx['destino'] = self.request.GET.get('destino') or self.request.user.email or ''
        ctx['emails_recentes'] = EmailLog.objects.order_by('-criado_em')[:15]
        return ctx


class MasterEmailTesteView(MasterRequiredMixin, View):
    def post(self, request):
        destino = (request.POST.get('destino') or '').strip()
        log_audit(request, 'email_teste', objeto='EmailLog', detalhes={'destino': mascarar_email(destino)})
        if not destino or '@' not in destino:
            messages.error(request, 'Informe um e-mail de destino válido.')
            return redirect('master_configuracoes')
        resultado = enviar_email(
            destino,
            'Teste SMTP da plataforma',
            'Este é um e-mail de teste do painel Master. Se você recebeu, o SMTP está funcionando.',
            tipo=EmailLog.TIPO_TESTE,
        )
        if resultado.ok:
            messages.success(request, 'E-mail de teste enviado.')
        elif resultado.status == 'NOT_CONFIGURED':
            messages.warning(request, 'E-mail não configurado neste ambiente.')
        else:
            motivo = (resultado.erro or 'Falha no envio.').strip()
            messages.error(request, f'Não foi possível enviar o e-mail. {motivo}')
        return redirect('master_configuracoes')


class MasterBuscaView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/busca.html'
    app_active = 'busca'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()[:80]
        ctx['q'] = q
        ctx['clientes'] = []
        ctx['portais'] = []
        ctx['assinaturas'] = []
        ctx['usuarios'] = []
        if len(q) >= 2:
            ctx['clientes'] = list(
                Cliente.objects.filter(Q(nome__icontains=q) | Q(email__icontains=q))[:20]
            )
            ctx['portais'] = list(
                Portal.objects.filter(
                    Q(nome__icontains=q) | Q(slug__icontains=q) | Q(custom_domain__icontains=q)
                )[:20]
            )
            ctx['assinaturas'] = list(
                Assinatura.objects.select_related('cliente', 'portal').filter(
                    Q(kiwify_order_id__icontains=q) | Q(kiwify_subscription_id__icontains=q)
                )[:20]
            )
            ctx['usuarios'] = list(
                User.objects.filter(Q(username__icontains=q) | Q(email__icontains=q))[:20]
            )
        return ctx


class MasterWebhooksView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/webhooks.html'
    model = WebhookEvent
    context_object_name = 'eventos'
    paginate_by = 20
    app_active = 'webhooks'

    def get_queryset(self):
        qs = WebhookEvent.objects.all()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(id_externo__icontains=q) | Q(tipo__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ids = [e.id_externo for e in ctx['eventos']]
        mapa = {
            a.kiwify_order_id: a
            for a in Assinatura.objects.filter(kiwify_order_id__in=ids).select_related('cliente')
        }
        for evento in ctx['eventos']:
            evento.assinatura_rel = mapa.get(evento.id_externo)
        return ctx


class MasterWebhookDetailView(MasterRequiredMixin, DetailView):
    template_name = 'plataforma/master/webhook_detalhe.html'
    model = WebhookEvent
    context_object_name = 'item'
    app_active = 'webhooks'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['payload_seguro'] = json.dumps(
            payload_publico(self.object.payload or {}),
            indent=2,
            ensure_ascii=False,
        )
        order_id = self.object.order_id_publico()
        sub_id = self.object.subscription_id_publico()
        ctx['assinatura'] = Assinatura.objects.filter(
            Q(kiwify_order_id=order_id) | Q(kiwify_subscription_id=sub_id)
        ).select_related('cliente', 'portal').first()
        return ctx


class MasterWebhookReprocessarView(MasterRequiredMixin, View):
    def get(self, request, pk):
        item = get_object_or_404(WebhookEvent, pk=pk)
        return render(request, 'plataforma/master/confirm_acao.html', {
            'is_master_shell': True,
            'app_active': 'webhooks',
            'titulo': 'Processar webhook novamente',
            'mensagem': f'Reprocessar o evento {item.tipo} ({item.id_externo})?',
            'action': reverse('master_webhook_reprocessar', args=[item.pk]),
            'voltar': reverse('master_webhook', args=[item.pk]),
        })

    def post(self, request, pk):
        item = get_object_or_404(WebhookEvent, pk=pk)
        log_audit(request, 'webhook_reprocessar', objeto='WebhookEvent', objeto_id=item.pk)
        if item.processado and item.status == WebhookEvent.STATUS_PROCESSADO:
            messages.info(request, 'Este evento já foi processado.')
            return redirect('master_webhook', pk=item.pk)
        resultado = processar_evento(item, payload=item.payload, request=request)
        if resultado.get('duplicado'):
            messages.info(request, 'Este evento já foi processado.')
        elif resultado.get('ok'):
            messages.success(request, 'Webhook processado novamente.')
        else:
            messages.error(request, 'Não foi possível processar o webhook. Consulte o diagnóstico.')
        return redirect('master_webhook', pk=item.pk)


class MasterClienteReenviarView(MasterRequiredMixin, View):
    def get(self, request, pk):
        item = get_object_or_404(Cliente, pk=pk)
        return render(request, 'plataforma/master/confirm_acao.html', {
            'is_master_shell': True,
            'app_active': 'clientes',
            'titulo': 'Reenviar acesso',
            'mensagem': f'Reenviar o e-mail de acesso para {item.email}?',
            'action': reverse('master_cliente_reenviar', args=[item.pk]),
            'voltar': reverse('master_cliente', args=[item.pk]),
        })

    def post(self, request, pk):
        item = get_object_or_404(Cliente, pk=pk)
        log_audit(request, 'reenvio_acesso', objeto='Cliente', objeto_id=item.pk)
        user = usuario_do_cliente(item)
        if user is None:
            messages.error(request, 'Este cliente ainda não tem usuário. Não é possível reenviar o acesso.')
            return redirect('master_cliente', pk=item.pk)
        if not item.email:
            messages.error(request, 'Cliente sem e-mail.')
            return redirect('master_cliente', pk=item.pk)
        portal = item.portais.order_by('id').first()
        resultado = enviar_acesso(
            user, portal, request=request, tipo=EmailLog.TIPO_REENVIO, cliente=item,
        )
        if resultado.ok:
            messages.success(request, '✅ Acesso reenviado com sucesso.')
        else:
            motivo = (resultado.erro or 'Falha no envio.').strip()
            messages.error(request, f'Não foi possível enviar o e-mail. {motivo}')
        return redirect('master_cliente', pk=item.pk)


class MasterAuditoriaView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/auditoria.html'
    model = AuditLog
    context_object_name = 'registros'
    paginate_by = 30
    app_active = 'auditoria'

    def get_queryset(self):
        qs = AuditLog.objects.select_related('usuario', 'portal')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(acao__icontains=q) | Q(objeto__icontains=q) | Q(usuario__username__icontains=q)
            )
        return qs
