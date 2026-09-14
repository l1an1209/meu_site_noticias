from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, TemplateView

from plataforma.security import log_audit, throttle_blocked, throttle_response

from .forms import CadastroForm, LoginForm
from .models import Perfil


class PortalAuthContextMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portal = getattr(self.request, 'portal', None)
        if portal is not None:
            ctx['site_name'] = portal.nome
        return ctx

    def get_form(self, form_class=None):
        get_form = getattr(super(), 'get_form', None)
        if get_form is None:
            return None
        form = get_form(form_class)
        if form is None:
            return form
        for field in form.fields.values():
            widget = field.widget
            input_type = getattr(widget, 'input_type', '')
            if input_type == 'checkbox':
                continue
            css = widget.attrs.get('class', '')
            if 'form-control' not in css:
                widget.attrs['class'] = f'{css} form-control'.strip()
        return form


class EntrarView(PortalAuthContextMixin, LoginView):
    template_name = 'noticias/entrar.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST' and throttle_blocked(
            request,
            'login',
            settings.LOGIN_THROTTLE_LIMIT,
            settings.LOGIN_THROTTLE_WINDOW,
        ):
            return throttle_response()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return self.get_redirect_url() or str(reverse_lazy('index'))


class SairView(View):
    """Logout via GET ou POST — evita página quebrada ao clicar em Sair."""

    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request):
        return self._sair(request)

    def post(self, request):
        return self._sair(request)

    def _sair(self, request):
        if request.user.is_authenticated:
            logout(request)
            messages.success(request, 'Você saiu da sua conta. Até logo!')
        return redirect('index')


class CadastroView(CreateView):
    form_class = CadastroForm
    template_name = 'noticias/cadastro.html'
    success_url = reverse_lazy('index')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('conta')
        if request.method == 'POST' and throttle_blocked(
            request,
            'cadastro',
            settings.SENSITIVE_THROTTLE_LIMIT,
            settings.SENSITIVE_THROTTLE_WINDOW,
        ):
            return throttle_response()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        log_audit(self.request, 'cadastro', objeto='User', objeto_id=self.object.pk)
        messages.success(
            self.request,
            'Conta criada! Agora você pode curtir, comentar e participar do portal.',
        )
        return response


class MinhaContaView(LoginRequiredMixin, TemplateView):
    template_name = 'noticias/conta.html'
    login_url = reverse_lazy('entrar')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        perfil, _ = Perfil.objects.get_or_create(usuario=self.request.user)
        context['perfil'] = perfil
        context['comentarios_count'] = self.request.user.comentarios.count()
        context['curtidas_count'] = self.request.user.curtidas.count()
        return context


class ParceriaView(TemplateView):
    template_name = 'noticias/parceria.html'


class RecuperarSenhaView(PortalAuthContextMixin, PasswordResetView):
    template_name = 'noticias/auth/password_reset_form.html'
    email_template_name = 'noticias/auth/password_reset_email.txt'
    subject_template_name = 'noticias/auth/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST' and throttle_blocked(
            request,
            'password_reset',
            settings.SENSITIVE_THROTTLE_LIMIT,
            settings.SENSITIVE_THROTTLE_WINDOW,
        ):
            return throttle_response()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        portal = getattr(self.request, 'portal', None)
        self.extra_email_context = {
            'site_name': portal.nome if portal else 'Portal',
        }
        return super().form_valid(form)


class RecuperarSenhaEnviadoView(PortalAuthContextMixin, PasswordResetDoneView):
    template_name = 'noticias/auth/password_reset_done.html'


class RedefinirSenhaView(PortalAuthContextMixin, PasswordResetConfirmView):
    template_name = 'noticias/auth/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class RedefinirSenhaConcluidoView(PortalAuthContextMixin, PasswordResetCompleteView):
    template_name = 'noticias/auth/password_reset_complete.html'


class AlterarSenhaView(PortalAuthContextMixin, PasswordChangeView):
    template_name = 'noticias/auth/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        log_audit(self.request, 'senha_alterar', objeto='User', objeto_id=self.request.user.pk)
        messages.success(self.request, 'Senha alterada. Use a nova senha no próximo acesso.')
        return super().form_valid(form)


class AlterarSenhaConcluidoView(PortalAuthContextMixin, PasswordChangeDoneView):
    template_name = 'noticias/auth/password_change_done.html'
