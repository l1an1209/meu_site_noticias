from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from plataforma.models import AdaptiveExperiment
from plataforma.services.adaptive_engine import (
    calcular,
    detectar,
    gerar,
    ler,
    sugerir_experimentos,
)
from plataforma.services.adaptive_engine.metrics import baseline_da_etapa
from plataforma.services.adaptive_engine.persistence import (
    criar_experimento,
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = _params_globais(self.request.GET)
        ctx['sugestoes'] = _pendentes(params)
        ctx['periodo'] = params.get('periodo', '')
        ctx['de'] = params.get('de', '')
        ctx['ate'] = params.get('ate', '')
        return ctx


class MasterExperimentoCriarView(MasterRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request):
        insight_id = (request.POST.get('insight_id') or '').strip()
        if not insight_id:
            messages.error(request, 'Informe a sugestão a persistir.')
            return redirect('master_experimentos')
        params = _params_globais(request.POST)
        sugestoes, por_id = _cadeia(params)
        insight = por_id.get(insight_id)
        sugestao = next((item for item in sugestoes if item.insight_id == insight_id), None)
        if insight is None or sugestao is None:
            messages.error(request, 'Sugestão não encontrada para o período observado.')
            return redirect('master_experimentos')
        ja_existia = AdaptiveExperiment.objects.filter(
            insight_id=insight_id,
            status__in=AdaptiveExperiment.STATUS_ATIVOS,
        ).exists()
        registro = criar_experimento(
            sugestao,
            area=insight.area,
            portal=None,
            **_baseline(insight.area),
        )
        if registro is None:
            messages.error(request, 'Não foi possível criar o experimento.')
            return redirect('master_experimentos')
        if ja_existia:
            link = reverse('master_experimento', args=[registro.pk])
            messages.warning(
                request,
                f'Já existe um experimento ativo para esta sugestão. {link}',
            )
        else:
            messages.success(request, 'Experimento criado — aguardando aprovação.')
        return redirect('master_experimentos')


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


def _params_globais(origem):
    params = {}
    for chave in ('periodo', 'de', 'ate'):
        valor = (origem.get(chave) or '').strip()
        if valor:
            params[chave] = valor
    return params


def _cadeia(params):
    ler(params)
    metricas = calcular(params)
    detectado = detectar(params)
    insights = gerar(metricas, detectado['gargalos'])
    sugestoes = sugerir_experimentos(insights)
    return sugestoes, {item.id: item for item in insights}


def _pendentes(params):
    sugestoes, por_id = _cadeia(params)
    ativos = set(
        AdaptiveExperiment.objects.filter(
            status__in=AdaptiveExperiment.STATUS_ATIVOS,
        ).values_list('insight_id', flat=True)
    )
    linhas = []
    for sugestao in sugestoes:
        insight = por_id.get(sugestao.insight_id)
        if insight is None or sugestao.insight_id in ativos:
            continue
        baseline = baseline_da_etapa(insight.area)
        linhas.append({
            'insight_id': sugestao.insight_id,
            'titulo': sugestao.titulo,
            'area': insight.area,
            'tipo': sugestao.tipo,
            'hipotese': sugestao.hipotese,
            'metrica_principal': sugestao.metrica_principal,
            'amostra': sugestao.amostra,
            'valor_baseline': None if baseline is None else baseline['valor_baseline'],
        })
    return linhas


def _baseline(area):
    baseline = baseline_da_etapa(area)
    if baseline is None:
        return {}
    return {
        'valor_baseline': baseline['valor_baseline'],
        'amostra_baseline': baseline['amostra_baseline'],
        'periodo_baseline_inicio': baseline['periodo_baseline_inicio'],
        'periodo_baseline_fim': baseline['periodo_baseline_fim'],
    }
