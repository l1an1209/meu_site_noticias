from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.timezone import localtime
from django.views import View
from django.views.generic import TemplateView

from plataforma.models import ConversaAjuda, MensagemAjuda
from plataforma.views_app import AppAccessMixin


def _payload_mensagem(msg):
    return {
        'id': msg.pk,
        'texto': msg.texto,
        'origem': msg.origem,
        'autor': msg.autor.get_username() if msg.autor_id else '',
        'criado_em': localtime(msg.criado_em).strftime('%d/%m/%Y %H:%M'),
    }


def _conversas_do_portal(request):
    return ConversaAjuda.objects.select_related('portal', 'aberto_por')


class AppAjudaListView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/ajuda.html'
    app_active = 'ajuda'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['conversas'] = list(_conversas_do_portal(self.request)[:80])
        ctx['tipos'] = ConversaAjuda.TIPO_CHOICES
        return ctx

    def post(self, request, *args, **kwargs):
        tipo = (request.POST.get('tipo') or ConversaAjuda.TIPO_DUVIDA).strip()
        tipos = {item[0] for item in ConversaAjuda.TIPO_CHOICES}
        if tipo not in tipos:
            tipo = ConversaAjuda.TIPO_DUVIDA
        assunto = (request.POST.get('assunto') or '').strip()[:140]
        texto = (request.POST.get('texto') or '').strip()
        if not assunto or not texto:
            messages.error(request, 'Informe o assunto e a mensagem.')
            return self.get(request, *args, **kwargs)
        conversa = ConversaAjuda.objects.create(
            portal=request.portal,
            aberto_por=request.user,
            tipo=tipo,
            assunto=assunto,
            status=ConversaAjuda.STATUS_AGUARDANDO_SUPORTE,
            nao_lidas_master=0,
            nao_lidas_cliente=0,
        )
        conversa.adicionar_mensagem(request.user, MensagemAjuda.ORIGEM_CLIENTE, texto)
        return redirect('app_ajuda_conversa', pk=conversa.pk)


class AppAjudaConversaView(AppAccessMixin, TemplateView):
    template_name = 'plataforma/app/ajuda_conversa.html'
    app_active = 'ajuda'

    def _conversa(self):
        return get_object_or_404(_conversas_do_portal(self.request), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conversa = self._conversa()
        conversa.marcar_lida_cliente()
        ctx['conversa'] = conversa
        ctx['mensagens'] = list(conversa.mensagens.select_related('autor'))
        return ctx

    def post(self, request, *args, **kwargs):
        conversa = self._conversa()
        texto = (request.POST.get('texto') or '').strip()
        if not texto:
            messages.error(request, 'Escreva uma mensagem.')
            return redirect('app_ajuda_conversa', pk=conversa.pk)
        conversa.adicionar_mensagem(request.user, MensagemAjuda.ORIGEM_CLIENTE, texto)
        conversa.marcar_lida_cliente()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            ultima = conversa.mensagens.order_by('-id').first()
            return JsonResponse({
                'ok': True,
                'mensagem': _payload_mensagem(ultima),
                'status': conversa.status,
                'status_label': conversa.get_status_display(),
            })
        return redirect('app_ajuda_conversa', pk=conversa.pk)


class AppAjudaPollView(AppAccessMixin, View):
    def get(self, request, pk):
        conversa = get_object_or_404(_conversas_do_portal(request), pk=pk)
        depois = request.GET.get('depois') or '0'
        try:
            depois_id = int(depois)
        except (TypeError, ValueError):
            depois_id = 0
        qs = conversa.mensagens.select_related('autor').filter(pk__gt=depois_id)
        conversa.marcar_lida_cliente()
        return JsonResponse({
            'ok': True,
            'status': conversa.status,
            'status_label': conversa.get_status_display(),
            'encerrada': conversa.status == ConversaAjuda.STATUS_ENCERRADA,
            'mensagens': [_payload_mensagem(m) for m in qs],
        })
