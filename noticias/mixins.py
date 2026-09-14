from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy

from plataforma.permissions import PAPEIS_MODERACAO, has_portal_role, is_platform_master


class AssinanteRequiredMixin(LoginRequiredMixin):
    login_url = reverse_lazy('entrar')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if is_platform_master(request.user) or getattr(request, 'membership', None):
            return super().dispatch(request, *args, **kwargs)
        perfil = getattr(request.user, 'perfil', None)
        if not perfil or not perfil.is_assinante:
            messages.warning(
                request,
                'Área exclusiva para assinantes e parceiros. Veja /parceria/ para fechar parceria.',
            )
            return redirect('parceria')
        return super().dispatch(request, *args, **kwargs)


class PortalRoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('entrar')
    papeis_permitidos = tuple(PAPEIS_MODERACAO)

    def test_func(self):
        return has_portal_role(self.request, *self.papeis_permitidos)
