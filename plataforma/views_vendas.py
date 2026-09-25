from django.http import Http404
from django.views import View
from django.views.generic import DetailView, TemplateView

from plataforma.models import Plano
from plataforma.resolvers import resolve_portal_from_host
from plataforma.views_analytics import CommercialAnalyticsMixin


class PaginaVendasView(CommercialAnalyticsMixin, TemplateView):
    template_name = 'plataforma/vendas.html'
    analytics_tipo = 'view_plans'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['planos_venda'] = Plano.objects.filter(ativo=True).exclude(preco_mensal=0)
        ctx['plano_gratuito'] = Plano.objects.filter(ativo=True, codigo='gratuito').first()
        ctx['is_sales_page'] = True
        return ctx


class PaginaHomeSaaSView(CommercialAnalyticsMixin, TemplateView):
    """Landing comercial da plataforma. Não é o jornal de um tenant."""

    template_name = 'plataforma/home.html'
    analytics_tipo = 'view_home'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_sales_page'] = True
        ctx['product_name'] = 'PortalUP'
        ctx['planos_venda'] = Plano.objects.filter(ativo=True).exclude(preco_mensal=0)
        ctx['plano_gratuito'] = Plano.objects.filter(ativo=True, codigo='gratuito').first()
        return ctx


class HomePublicaView(View):
    """`/` no host da plataforma = landing SaaS. `/` no host do cliente = portal."""

    def dispatch(self, request, *args, **kwargs):
        if resolve_portal_from_host(request.get_host()) is None:
            return PaginaHomeSaaSView.as_view()(request, *args, **kwargs)
        from noticias.views import NoticiaListView
        return NoticiaListView.as_view()(request, *args, **kwargs)


class PaginaCheckoutPlanoView(CommercialAnalyticsMixin, DetailView):
    """Passo de contratação de um plano específico, antes do checkout Kiwify."""

    template_name = 'plataforma/checkout_plano.html'
    analytics_tipo = 'initiate_checkout'
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


class PaginaInstitucionalView(CommercialAnalyticsMixin, TemplateView):
    """Páginas legais do SaaS. Somente no host da plataforma."""

    def dispatch(self, request, *args, **kwargs):
        if resolve_portal_from_host(request.get_host()) is not None:
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class PaginaPrivacidadeView(PaginaInstitucionalView):
    template_name = 'plataforma/privacidade.html'


class PaginaTermosView(PaginaInstitucionalView):
    template_name = 'plataforma/termos.html'


class PaginaContatoView(PaginaInstitucionalView):
    template_name = 'plataforma/contato.html'
