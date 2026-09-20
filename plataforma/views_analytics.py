import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from plataforma.models import AnalyticsSession
from plataforma.services.analytics import (
    anexar_page_view,
    gravar_cookie,
    host_comercial,
    montar_dashboard,
    portal_filtrado,
    registrar_evento,
    sessoes_ativas,
)
from plataforma.views_master import MasterRequiredMixin


class CommercialAnalyticsMixin:
    """Page view no funil comercial. Não se aplica a tenants."""

    analytics_tipo = None

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return anexar_page_view(request, response, tipo=self.analytics_tipo)


@require_POST
def collect_analytics(request):
    if not host_comercial(request):
        return JsonResponse({'ok': False}, status=404)
    try:
        dados = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        dados = request.POST.dict()
    tipo = (dados.get('tipo') or dados.get('event') or '').strip()
    sessao = registrar_evento(
        request,
        tipo,
        path=dados.get('path') or request.path,
        extra=dados,
        ref_externo=dados.get('eid') or '',
    )
    resp = JsonResponse({'ok': True})
    if sessao:
        gravar_cookie(resp, sessao)
    return resp


class MasterAnalyticsView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/analytics.html'
    app_active = 'analytics'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(montar_dashboard(self.request.GET))
        ctx['gerado_em'] = now()
        return ctx


class MasterAnalyticsAgoraView(MasterRequiredMixin, View):
    def get(self, request):
        portal = portal_filtrado(request.GET)
        instante = now()
        itens = []
        for sessao in sessoes_ativas(portal)[:40]:
            segundos = max(0, int((instante - sessao.visto_em).total_seconds()))
            itens.append({
                'id': str(sessao.id),
                'rotulo': sessao.rotulo,
                'origem': sessao.origem_label(),
                'dispositivo': sessao.get_dispositivo_display(),
                'path': sessao.path_atual or '/',
                'segundos': segundos,
            })
        return JsonResponse({'ok': True, 'ativos': len(itens), 'itens': itens})


class MasterAnalyticsSessaoView(MasterRequiredMixin, TemplateView):
    template_name = 'plataforma/master/analytics_sessao.html'
    app_active = 'analytics'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sessao = get_object_or_404(AnalyticsSession, pk=kwargs['pk'])
        ctx['sessao'] = sessao
        ctx['jornada'] = list(sessao.eventos.all())
        return ctx
