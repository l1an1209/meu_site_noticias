from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.timezone import localtime
from django.views import View
from django.views.generic import ListView, TemplateView

from plataforma.models import ConversaAjuda, MensagemAjuda
from plataforma.views_master import MasterRequiredMixin


def _payload_mensagem(msg):
    return {
        'id': msg.pk,
        'texto': msg.texto,
        'origem': msg.origem,
        'autor': msg.autor.get_username() if msg.autor_id else '',
        'criado_em': localtime(msg.criado_em).strftime('%d/%m/%Y %H:%M'),
    }


def _conversas_master():
    return ConversaAjuda.all_objects.select_related(
        'portal', 'portal__cliente', 'aberto_por',
    )


class MasterAtendimentoListView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/atendimento.html'
    context_object_name = 'conversas'
    paginate_by = 30
    app_active = 'atendimento'

    def get_queryset(self):
        qs = _conversas_master()
        status = (self.request.GET.get('status') or '').strip()
        if status:
            qs = qs.filter(status=status)
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(assunto__icontains=q)
                | Q(portal__nome__icontains=q)
                | Q(portal__slug__icontains=q)
                | Q(portal__cliente_email__icontains=q)
                | Q(portal__cliente__email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtro_status'] = self.request.GET.get('status') or ''
        ctx['status_choices'] = ConversaAjuda.STATUS_CHOICES
        return ctx


class MasterAtendimentoConversaView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/atendimento_conversa.html'
    app_active = 'atendimento'

    def _conversa(self):
        return get_object_or_404(_conversas_master(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conversa = self._conversa()
        conversa.marcar_lida_master()
        ctx['conversa'] = conversa
        ctx['mensagens'] = list(conversa.mensagens.select_related('autor'))
        ctx['status_choices'] = ConversaAjuda.STATUS_CHOICES
        return ctx

    def post(self, request, *args, **kwargs):
        conversa = self._conversa()
        acao = (request.POST.get('acao') or 'responder').strip()
        if acao == 'status':
            try:
                conversa.definir_status(request.POST.get('status'))
                messages.success(request, 'Status atualizado.')
            except ValueError:
                messages.error(request, 'Não foi possível alterar o status.')
            return redirect('master_atendimento_conversa', pk=conversa.pk)
        texto = (request.POST.get('texto') or '').strip()
        if not texto:
            messages.error(request, 'Escreva uma mensagem.')
            return redirect('master_atendimento_conversa', pk=conversa.pk)
        conversa.adicionar_mensagem(request.user, MensagemAjuda.ORIGEM_SUPORTE, texto)
        conversa.marcar_lida_master()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            ultima = conversa.mensagens.order_by('-id').first()
            return JsonResponse({
                'ok': True,
                'mensagem': _payload_mensagem(ultima),
                'status': conversa.status,
                'status_label': conversa.get_status_display(),
            })
        return redirect('master_atendimento_conversa', pk=conversa.pk)


class MasterAtendimentoPollView(MasterRequiredMixin, View):
    def get(self, request, pk):
        conversa = get_object_or_404(_conversas_master(), pk=pk)
        depois = request.GET.get('depois') or '0'
        try:
            depois_id = int(depois)
        except (TypeError, ValueError):
            depois_id = 0
        qs = conversa.mensagens.select_related('autor').filter(pk__gt=depois_id)
        conversa.marcar_lida_master()
        return JsonResponse({
            'ok': True,
            'status': conversa.status,
            'status_label': conversa.get_status_display(),
            'encerrada': conversa.status == ConversaAjuda.STATUS_ENCERRADA,
            'mensagens': [_payload_mensagem(m) for m in qs],
        })
