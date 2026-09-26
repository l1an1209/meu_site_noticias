from django.urls import path

from plataforma.views_master import (
    MasterAssinaturasView,
    MasterClienteDetailView,
    MasterClientesView,
    MasterHomeView,
    MasterPlanoUpdateView,
    MasterMonetizacaoView,
    MasterPlanosView,
    MasterPortalAcaoView,
    MasterPortalDetailView,
    MasterPortaisView,
)
from plataforma.views_master_ops import (
    MasterAuditoriaView,
    MasterBuscaView,
    MasterClienteReenviarView,
    MasterConfiguracoesView,
    MasterEmailTesteView,
    MasterSaudeView,
    MasterWebhookDetailView,
    MasterWebhookReprocessarView,
    MasterWebhooksView,
)
from plataforma.views_analytics import (
    MasterAnalyticsAgoraView,
    MasterAnalyticsSessaoView,
    MasterAnalyticsView,
)
from plataforma.views_experimentos import (
    MasterExperimentoCriarView,
    MasterExperimentoDetailView,
    MasterExperimentosView,
)
from plataforma.views_master_ajuda import (
    MasterAtendimentoConversaView,
    MasterAtendimentoListView,
    MasterAtendimentoPollView,
)

urlpatterns = [
    path('', MasterHomeView.as_view(), name='master_home'),
    path('busca/', MasterBuscaView.as_view(), name='master_busca'),
    path('saude/', MasterSaudeView.as_view(), name='master_saude'),
    path('configuracoes/', MasterConfiguracoesView.as_view(), name='master_configuracoes'),
    path('configuracoes/email-teste/', MasterEmailTesteView.as_view(), name='master_email_teste'),
    path('webhooks/', MasterWebhooksView.as_view(), name='master_webhooks'),
    path('webhooks/<int:pk>/', MasterWebhookDetailView.as_view(), name='master_webhook'),
    path('webhooks/<int:pk>/reprocessar/', MasterWebhookReprocessarView.as_view(), name='master_webhook_reprocessar'),
    path('auditoria/', MasterAuditoriaView.as_view(), name='master_auditoria'),
    path('analytics/', MasterAnalyticsView.as_view(), name='master_analytics'),
    path('experimentos/', MasterExperimentosView.as_view(), name='master_experimentos'),
    path('experimentos/criar/', MasterExperimentoCriarView.as_view(), name='master_experimento_criar'),
    path('experimentos/<int:pk>/', MasterExperimentoDetailView.as_view(), name='master_experimento'),
    path('analytics/agora/', MasterAnalyticsAgoraView.as_view(), name='master_analytics_agora'),
    path('analytics/sessoes/<uuid:pk>/', MasterAnalyticsSessaoView.as_view(), name='master_analytics_sessao'),
    path('clientes/', MasterClientesView.as_view(), name='master_clientes'),
    path('clientes/<int:pk>/', MasterClienteDetailView.as_view(), name='master_cliente'),
    path('clientes/<int:pk>/reenviar/', MasterClienteReenviarView.as_view(), name='master_cliente_reenviar'),
    path('portais/', MasterPortaisView.as_view(), name='master_portais'),
    path('portais/<int:pk>/', MasterPortalDetailView.as_view(), name='master_portal'),
    path('portais/<int:pk>/acao/', MasterPortalAcaoView.as_view(), name='master_portal_acao'),
    path('assinaturas/', MasterAssinaturasView.as_view(), name='master_assinaturas'),
    path('monetizacao/', MasterMonetizacaoView.as_view(), name='master_monetizacao'),
    path('planos/', MasterPlanosView.as_view(), name='master_planos'),
    path('planos/<int:pk>/', MasterPlanoUpdateView.as_view(), name='master_plano'),
    path('atendimento/', MasterAtendimentoListView.as_view(), name='master_atendimento'),
    path('atendimento/<int:pk>/', MasterAtendimentoConversaView.as_view(), name='master_atendimento_conversa'),
    path('atendimento/<int:pk>/mensagens/', MasterAtendimentoPollView.as_view(), name='master_atendimento_poll'),
]
