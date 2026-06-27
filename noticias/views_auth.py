from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import login
from .forms import CadastroForm, LoginForm
from .models import Perfil


class EntrarView(LoginView):
    template_name = 'noticias/entrar.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        return next_url or str(reverse_lazy('index'))


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
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
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
