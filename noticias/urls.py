from django.urls import path
from plataforma.views_app import AppAprovarEnvioView, AppEnviosView, AppRejeitarEnvioView
from plataforma.views_pos_login import AcessoPortalIndisponivelView, SelecionarPortalView
from plataforma.views_vendas import HomePublicaView
from .views import (
    NoticiaDetailView,
    NoticiaPorCategoriaListView,
    NoticiaVideoListView,
    ContribuicaoCreateView,
)
from .views_auth import (
    AlterarSenhaConcluidoView,
    AlterarSenhaView,
    CadastroView,
    EntrarView,
    MinhaContaView,
    ParceriaView,
    RecuperarSenhaEnviadoView,
    RecuperarSenhaView,
    RedefinirSenhaConcluidoView,
    RedefinirSenhaView,
    SairView,
)
from .views_engagement import toggle_curtida, adicionar_comentario
from .views_exclusivo import ExclusivoListView, ExclusivoDetailView
from .views_experiencia import ExperienciaView, ClimaApiView

urlpatterns = [
    path('', HomePublicaView.as_view(), name='index'),
    path('videos/', NoticiaVideoListView.as_view(), name='videos'),
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
    path('criar-conta/', CadastroView.as_view(), name='criar_conta'),
    path('selecionar-portal/', SelecionarPortalView.as_view(), name='selecionar_portal'),
    path('acesso-indisponivel/', AcessoPortalIndisponivelView.as_view(), name='acesso_portal_indisponivel'),
    path('conta/', MinhaContaView.as_view(), name='conta'),
    path('senha/esqueci/', RecuperarSenhaView.as_view(), name='password_reset'),
    path('senha/enviado/', RecuperarSenhaEnviadoView.as_view(), name='password_reset_done'),
    path('senha/redefinir/<uidb64>/<token>/', RedefinirSenhaView.as_view(), name='password_reset_confirm'),
    path('senha/concluido/', RedefinirSenhaConcluidoView.as_view(), name='password_reset_complete'),
    path('senha/alterar/', AlterarSenhaView.as_view(), name='password_change'),
    path('senha/alterada/', AlterarSenhaConcluidoView.as_view(), name='password_change_done'),
    path('parceria/', ParceriaView.as_view(), name='parceria'),
    path('painel/', AppEnviosView.as_view(), name='painel'),
    path('painel/aprovar/<int:pk>/', AppAprovarEnvioView.as_view(), name='aprovar_envio'),
    path('painel/rejeitar/<int:pk>/', AppRejeitarEnvioView.as_view(), name='rejeitar_envio'),
]
