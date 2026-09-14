from django.urls import path

from plataforma.views_master import (
    MasterAssinaturasView,
    MasterClienteDetailView,
    MasterClientesView,
    MasterHomeView,
    MasterPlanoUpdateView,
    MasterPlanosView,
    MasterPortalAcaoView,
    MasterPortalDetailView,
    MasterPortaisView,
)

urlpatterns = [
    path('', MasterHomeView.as_view(), name='master_home'),
    path('clientes/', MasterClientesView.as_view(), name='master_clientes'),
    path('clientes/<int:pk>/', MasterClienteDetailView.as_view(), name='master_cliente'),
    path('portais/', MasterPortaisView.as_view(), name='master_portais'),
    path('portais/<int:pk>/', MasterPortalDetailView.as_view(), name='master_portal'),
    path('portais/<int:pk>/acao/', MasterPortalAcaoView.as_view(), name='master_portal_acao'),
    path('assinaturas/', MasterAssinaturasView.as_view(), name='master_assinaturas'),
    path('planos/', MasterPlanosView.as_view(), name='master_planos'),
    path('planos/<int:pk>/', MasterPlanoUpdateView.as_view(), name='master_plano'),
]
