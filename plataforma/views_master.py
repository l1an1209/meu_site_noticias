from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from noticias.models import Noticia
from plataforma.metrics import format_mb, storage_bytes_portal
from plataforma.models import (
    Assinatura, Cliente, ConfiguracaoMonetizacao, ConversaAjuda, EmailLog,
    Membership, Plano, Portal, WebhookEvent,
)
from plataforma.permissions import is_platform_master
from plataforma.security import log_audit
from plataforma.services.acesso import usuario_do_cliente
from plataforma.services.onboarding import master_alterar_plano, master_definir_status_portal
from plataforma.services.publicidade import limpar_cache_monetizacao, resumo_rede
from plataforma.services.saude import problemas_operacao
from plataforma.services.timeline import timeline_cliente


class MasterRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('entrar')
    raise_exception = False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.get_permission_denied_message())
        return super().handle_no_permission()

    def test_func(self):
        return is_platform_master(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['app_active'] = getattr(self, 'app_active', '')
        ctx['is_master_shell'] = True
        ctx['atendimento_nao_lidas'] = (
            ConversaAjuda.all_objects.aggregate(n=Sum('nao_lidas_master'))['n'] or 0
        )
        return ctx


class MasterHomeView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/dashboard.html'
    app_active = 'home'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portais = Portal.objects.select_related('plano', 'cliente')
        ativas = Assinatura.objects.filter(status=Assinatura.STATUS_ATIVA)
        receita = ativas.aggregate(total=Sum('plano__preco_mensal'))['total']
        ctx.update({
            'total_portais': portais.count(),
            'portais_ativos': portais.filter(status=Portal.STATUS_ATIVO).count(),
            'portais_bloqueados': portais.filter(status=Portal.STATUS_BLOQUEADO).count(),
            'total_noticias': Noticia.all_objects.count(),
            'total_membros': Membership.objects.count(),
            'total_clientes': Cliente.objects.filter(status=Cliente.STATUS_ATIVO).count(),
            'assinaturas_ativas': ativas.count(),
            'pagamentos_pendentes': Assinatura.objects.filter(
                status__in=[Assinatura.STATUS_PENDENTE, Assinatura.STATUS_AGUARDANDO],
            ).count(),
            'assinaturas_atrasadas': Assinatura.objects.filter(
                status=Assinatura.STATUS_ATRASADA,
            ).count(),
            'clientes_bloqueados': Cliente.objects.filter(status=Cliente.STATUS_INATIVO).count(),
            'emails_falha': EmailLog.objects.filter(status=EmailLog.STATUS_FALHOU).count(),
            'webhooks_erro': WebhookEvent.objects.filter(status=WebhookEvent.STATUS_ERRO).count(),
            'receita_recorrente': receita,
            'problemas': problemas_operacao(),
            'portais': list(portais[:50]),
        })
        for p in ctx['portais']:
            p.noticias_n = Noticia.all_objects.filter(portal=p).count()
            p.storage_mb = format_mb(storage_bytes_portal(p))
        return ctx


class MasterPortaisView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/portais.html'
    model = Portal
    context_object_name = 'portais'
    paginate_by = 20
    app_active = 'portais'

    def get_queryset(self):
        qs = Portal.objects.select_related('plano', 'cliente').annotate(
            n_noticias=Count('noticias', distinct=True),
            n_membros=Count('membros', distinct=True),
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nome__icontains=q) | Q(slug__icontains=q) | Q(cidade__icontains=q)
            )
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class MasterPortalDetailView(MasterRequiredMixin, DetailView):
    template_name = 'plataforma/master/portal_detalhe.html'
    model = Portal
    context_object_name = 'item'
    app_active = 'portais'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        p = self.object
        ctx['n_noticias'] = Noticia.all_objects.filter(portal=p).count()
        ctx['membros'] = Membership.objects.filter(portal=p).select_related('usuario')
        ctx['storage_mb'] = format_mb(storage_bytes_portal(p))
        ctx['assinatura'] = p.assinatura_atual()
        ctx['planos'] = Plano.objects.filter(ativo=True)
        return ctx


class MasterClientesView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/clientes.html'
    model = Cliente
    context_object_name = 'clientes'
    paginate_by = 20
    app_active = 'clientes'

    def get_queryset(self):
        ultimo = EmailLog.objects.filter(
            Q(cliente_id=OuterRef('pk')) | Q(destinatario=OuterRef('email')),
        ).order_by('-criado_em')
        qs = Cliente.objects.annotate(
            n_portais=Count('portais', distinct=True),
            ultimo_email_status=Subquery(ultimo.values('status')[:1]),
            ultimo_email_tipo=Subquery(ultimo.values('tipo')[:1]),
            ultimo_email_em=Subquery(ultimo.values('enviado_em')[:1]),
            ultimo_email_tentativas=Subquery(ultimo.values('tentativas')[:1]),
        ).order_by('nome')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(email__icontains=q) | Q(telefone__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class MasterClienteDetailView(MasterRequiredMixin, DetailView):
    template_name = 'plataforma/master/cliente_detalhe.html'
    model = Cliente
    context_object_name = 'item'
    app_active = 'clientes'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['portais'] = self.object.portais.select_related('plano')
        ctx['assinaturas'] = self.object.assinaturas.select_related('portal', 'plano')
        ctx['usuario'] = usuario_do_cliente(self.object)
        ctx['ultimo_email'] = self.object.emails.order_by('-criado_em').first()
        ctx['tentativas_acesso'] = self.object.emails.filter(
            tipo__in=[EmailLog.TIPO_ONBOARDING, EmailLog.TIPO_REENVIO],
        ).count()
        ctx['timeline'] = timeline_cliente(self.object)
        return ctx


class MasterAssinaturasView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/assinaturas.html'
    model = Assinatura
    context_object_name = 'assinaturas'
    paginate_by = 20
    app_active = 'assinaturas'

    def get_queryset(self):
        qs = Assinatura.objects.select_related('cliente', 'portal', 'plano')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(cliente__email__icontains=q)
                | Q(cliente__nome__icontains=q)
                | Q(portal__slug__icontains=q)
                | Q(kiwify_order_id__icontains=q)
                | Q(kiwify_subscription_id__icontains=q)
            )
        return qs


class MasterPlanosView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/planos.html'
    model = Plano
    context_object_name = 'planos'
    app_active = 'planos'


class MasterPlanoUpdateView(MasterRequiredMixin, UpdateView):
    template_name = 'plataforma/app/form.html'
    model = Plano
    fields = [
        'nome', 'descricao', 'recursos', 'preco_mensal', 'ativo', 'ordem',
        'max_storage_mb', 'max_usuarios', 'kiwify_product_id', 'kiwify_plan_id',
        'checkout_url',
    ]
    success_url = reverse_lazy('master_planos')
    app_active = 'planos'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'Plano {self.object.nome}'
        return ctx

    def form_valid(self, form):
        log_audit(
            self.request, 'plano_alterar', objeto='Plano', objeto_id=self.object.pk,
            detalhes={'codigo': self.object.codigo},
        )
        messages.success(self.request, 'Plano atualizado.')
        return super().form_valid(form)


class MasterMonetizacaoView(MasterRequiredMixin, UpdateView):
    template_name = 'plataforma/master/monetizacao.html'
    model = ConfiguracaoMonetizacao
    fields = [
        'ativa', 'provedor', 'publisher_id', 'codigo_script',
        'publicidade_gratuito', 'publicidade_pago',
    ]
    success_url = reverse_lazy('master_monetizacao')
    app_active = 'monetizacao'

    def get_object(self, queryset=None):
        return ConfiguracaoMonetizacao.obter()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(resumo_rede())
        ctx['posicoes_conhecidas'] = ConfiguracaoMonetizacao.POSICOES
        return ctx

    def form_valid(self, form):
        posicoes = self.request.POST.getlist('posicoes')
        permitidas = [p for p in posicoes if p in ConfiguracaoMonetizacao.POSICOES]
        form.instance.posicoes = permitidas
        messages.success(self.request, 'Monetização atualizada.')
        log_audit(self.request, 'monetizacao_alterar', objeto='ConfiguracaoMonetizacao', objeto_id=1)
        response = super().form_valid(form)
        limpar_cache_monetizacao()
        return response


class MasterPortalAcaoView(MasterRequiredMixin, View):
    def post(self, request, pk):
        portal = get_object_or_404(Portal, pk=pk)
        acao = request.POST.get('acao')
        if acao in {'ativar', 'reativar'}:
            master_definir_status_portal(portal, True, request=request)
            messages.success(request, f'{portal.nome} está ativo. O conteúdo foi preservado.')
        elif acao == 'bloquear':
            master_definir_status_portal(portal, False, request=request)
            messages.warning(request, f'{portal.nome} bloqueado. Nada foi apagado.')
        elif acao == 'plano':
            plano = get_object_or_404(Plano, pk=request.POST.get('plano_id'))
            master_alterar_plano(portal, plano, request=request)
            messages.success(request, f'Plano de {portal.nome} agora é {plano.nome}.')
        elif acao == 'publicidade':
            modo = request.POST.get('publicidade_modo', '')
            permitidos = {item[0] for item in Portal.PUBLICIDADE_MODO_CHOICES}
            if modo not in permitidos:
                messages.error(request, 'Modo de publicidade inválido.')
            else:
                portal.publicidade_modo = modo
                portal.save(update_fields=['publicidade_modo'])
                limpar_cache_monetizacao()
                messages.success(request, 'Publicidade deste portal atualizada.')
        else:
            messages.error(request, 'Ação inválida.')
        return redirect('master_portal', pk=portal.pk)
