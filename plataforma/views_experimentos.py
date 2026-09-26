from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView

from plataforma.models import AdaptiveExperiment
from plataforma.services.adaptive_engine.persistence import (
    listar_experimentos,
    pode_transicionar,
    transicionar,
)
from plataforma.views_master import MasterRequiredMixin

_ACOES = {
    'aprovar': AdaptiveExperiment.STATUS_APROVADO,
    'iniciar': AdaptiveExperiment.STATUS_EXECUTANDO,
    'concluir': AdaptiveExperiment.STATUS_CONCLUIDO,
    'cancelar': AdaptiveExperiment.STATUS_CANCELADO,
}


class MasterExperimentosView(MasterRequiredMixin, ListView):
    template_name = 'plataforma/master/experimentos.html'
    context_object_name = 'experimentos'
    app_active = 'experimentos'

    def get_queryset(self):
        return listar_experimentos()


class MasterExperimentoDetailView(MasterRequiredMixin, DetailView):
    model = AdaptiveExperiment
    template_name = 'plataforma/master/experimento.html'
    context_object_name = 'experimento'
    app_active = 'experimentos'

    def post(self, request, pk):
        experimento = get_object_or_404(AdaptiveExperiment, pk=pk)
        destino = _ACOES.get(request.POST.get('acao'))
        if destino is None or not pode_transicionar(experimento.status, destino):
            messages.error(request, 'Transição não permitida.')
            return redirect('master_experimento', pk=experimento.pk)
        transicionar(experimento, destino)
        return redirect('master_experimento', pk=experimento.pk)
