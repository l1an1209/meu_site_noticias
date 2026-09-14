from django.views.generic import TemplateView

from plataforma.models import Plano


class PaginaVendasView(TemplateView):
    template_name = 'plataforma/vendas.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['planos_venda'] = Plano.objects.filter(ativo=True).exclude(preco_mensal=0)
        ctx['is_sales_page'] = True
        return ctx
