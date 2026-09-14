from django.views.generic import ListView
from django.contrib import messages
from django.shortcuts import redirect
from .models import Noticia
from .mixins import AssinanteRequiredMixin
from .views import NoticiasBaseMixin, NoticiaDetailView, _qs_noticias


class ExclusivoListView(AssinanteRequiredMixin, NoticiasBaseMixin, ListView):
    model = Noticia
    template_name = 'noticias/exclusivo.html'
    context_object_name = 'noticias'
    paginate_by = 8

    def get_queryset(self):
        return (
            _qs_noticias()
            .filter(exclusivo_assinantes=True)
            .order_by('-data_publicacao')
        )


class ExclusivoDetailView(NoticiaDetailView):
    def get_queryset(self):
        return _qs_noticias().filter(exclusivo_assinantes=True)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/entrar/?next={request.path}')
        perfil = getattr(request.user, 'perfil', None)
        if not request.user.is_staff and (not perfil or not perfil.is_assinante):
            messages.warning(request, 'Conteúdo exclusivo para assinantes.')
            return redirect('parceria')
        return super(NoticiaDetailView, self).dispatch(request, *args, **kwargs)
