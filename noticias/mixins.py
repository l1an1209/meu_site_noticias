from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy


class AssinanteRequiredMixin(LoginRequiredMixin):
    login_url = reverse_lazy('entrar')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        perfil = getattr(request.user, 'perfil', None)
        if not perfil or not perfil.is_assinante:
            if not request.user.is_staff:
                messages.warning(
                    request,
                    'Área exclusiva para assinantes e parceiros. Veja /parceria/ para fechar parceria.',
                )
                return redirect('parceria')
        return super().dispatch(request, *args, **kwargs)
