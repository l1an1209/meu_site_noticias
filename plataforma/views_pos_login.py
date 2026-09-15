from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from plataforma.models import Portal
from plataforma.permissions import is_platform_master
from plataforma.services.pos_login import (
    app_url_for_portal,
    portais_administraveis,
    portais_indisponiveis,
)


class SelecionarPortalView(LoginRequiredMixin, View):
    login_url = reverse_lazy('entrar')
    template_name = 'plataforma/selecionar_portal.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_platform_master(request.user):
            return redirect('master_home')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        portais = list(portais_administraveis(request.user))
        if not portais:
            if portais_indisponiveis(request.user).exists():
                return redirect('acesso_portal_indisponivel')
            return redirect('pagina_vendas')
        if len(portais) == 1:
            return redirect(app_url_for_portal(request, portais[0]))
        return render(request, self.template_name, {'portais': portais})

    def post(self, request):
        try:
            pk = int(request.POST.get('portal') or 0)
        except (TypeError, ValueError):
            pk = 0
        portal = portais_administraveis(request.user).filter(pk=pk).first()
        if portal is None:
            raise PermissionDenied('Portal não autorizado.')
        return redirect(app_url_for_portal(request, portal))


class AcessoPortalIndisponivelView(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy('entrar')
    template_name = 'plataforma/acesso_indisponivel.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['portais'] = list(portais_indisponiveis(self.request.user))
        return ctx
