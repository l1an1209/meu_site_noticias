from django.urls import path
from .views import (
    NoticiaListView,
    NoticiaDetailView,
    NoticiaPorCategoriaListView,
    ContribuicaoCreateView,
    PainelModeracaoView,
    AprovarEnvioView,
    RejeitarEnvioView,
)
from .views_auth import EntrarView, SairView, CadastroView, MinhaContaView, ParceriaView
from .views_engagement import toggle_curtida, adicionar_comentario
from .views_exclusivo import ExclusivoListView, ExclusivoDetailView
from .views_experiencia import ExperienciaView, ClimaApiView

urlpatterns = [
    path('', NoticiaListView.as_view(), name='index'),
    path('experiencia/', ExperienciaView.as_view(), name='experiencia'),
    path('api/clima/', ClimaApiView.as_view(), name='api_clima'),
    path('exclusivo/', ExclusivoListView.as_view(), name='exclusivo'),
    path('exclusivo/noticia/<int:id>/', ExclusivoDetailView.as_view(), name='exclusivo_detalhe'),
    path('noticia/<int:id>/', NoticiaDetailView.as_view(), name='detalhe'),
    path('noticia/<int:noticia_id>/curtir/', toggle_curtida, name='curtir'),
    path('noticia/<int:noticia_id>/comentar/', adicionar_comentario, name='comentar'),
    path('categoria/<slug:slug>/', NoticiaPorCategoriaListView.as_view(), name='noticias_por_categoria'),
    path('contribuir/', ContribuicaoCreateView.as_view(), name='contribuir'),
    path('entrar/', EntrarView.as_view(), name='entrar'),
    path('sair/', SairView.as_view(), name='sair'),
    path('cadastro/', CadastroView.as_view(), name='cadastro'),
    path('conta/', MinhaContaView.as_view(), name='conta'),
    path('parceria/', ParceriaView.as_view(), name='parceria'),
    path('painel/', PainelModeracaoView.as_view(), name='painel'),
    path('painel/aprovar/<int:pk>/', AprovarEnvioView.as_view(), name='aprovar_envio'),
    path('painel/rejeitar/<int:pk>/', RejeitarEnvioView.as_view(), name='rejeitar_envio'),
]
