from django.views.generic import DetailView, TemplateView

from plataforma.models import Plano


class PaginaVendasView(TemplateView):
    template_name = 'plataforma/vendas.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['planos_venda'] = Plano.objects.filter(ativo=True).exclude(preco_mensal=0)
        ctx['is_sales_page'] = True
        return ctx


class PaginaCheckoutPlanoView(DetailView):
    """Passo de contratação de um plano específico, antes do checkout Kiwify."""

    template_name = 'plataforma/checkout_plano.html'
    context_object_name = 'plano'
    slug_field = 'codigo'
    slug_url_kwarg = 'codigo'

    def get_queryset(self):
        return Plano.objects.filter(ativo=True).exclude(preco_mensal=0)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_sales_page'] = True
        ctx['cta_plano'] = f'Começar com o {self.object.nome}'
        return ctx
