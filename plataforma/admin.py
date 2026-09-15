from django.contrib import admin
from plataforma.admin_mixins import SuperuserOnlyAdminMixin
from .models import AuditLog, Assinatura, Cliente, EmailLog, Membership, Plano, Portal, WebhookEvent


@admin.register(Plano)
class PlanoAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'codigo', 'preco_mensal', 'max_storage_mb', 'max_usuarios', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome', 'codigo', 'kiwify_product_id', 'kiwify_plan_id')
    prepopulated_fields = {'codigo': ('nome',)}


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ('usuario',)


@admin.register(Portal)
class PortalAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        'nome', 'slug', 'cidade', 'estado', 'status',
        'plano', 'pagamento_status', 'criado_em',
    )
    list_filter = ('status', 'pagamento_status', 'estado', 'plano')
    search_fields = ('nome', 'slug', 'cidade', 'cliente_nome', 'cliente_email')
    prepopulated_fields = {'slug': ('nome',)}
    inlines = (MembershipInline,)
    readonly_fields = ('criado_em', 'ultimo_acesso_em')
    fieldsets = (
        ('Portal', {
            'fields': ('nome', 'slug', 'custom_domain', 'status', 'plano', 'pagamento_status'),
        }),
        ('Local', {
            'fields': ('cidade', 'estado', 'regiao', 'endereco', 'latitude', 'longitude'),
        }),
        ('Identidade', {
            'fields': (
                'slogan', 'tagline', 'descricao', 'texto_rodape',
                'logo', 'favicon', 'imagem_compartilhamento',
                'cor_primaria', 'cor_secundaria', 'cor_destaque',
            ),
        }),
        ('Contato e redes', {
            'fields': (
                'email', 'telefone', 'whatsapp',
                'facebook', 'instagram', 'youtube', 'twitter', 'tiktok',
            ),
        }),
        ('SEO e anúncios', {
            'fields': ('seo_title', 'seo_description', 'adsense_client_id'),
        }),
        ('Cliente', {
            'fields': ('cliente', 'cliente_nome', 'cliente_email', 'criado_em', 'ultimo_acesso_em'),
        }),
    )


@admin.register(Membership)
class MembershipAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('usuario', 'portal', 'papel', 'ativo', 'criado_em')
    list_filter = ('papel', 'ativo', 'portal')
    search_fields = ('usuario__username', 'usuario__email', 'portal__slug')
    autocomplete_fields = ('usuario', 'portal')


@admin.register(AuditLog)
class AuditLogAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('criado_em', 'acao', 'usuario', 'portal', 'objeto', 'objeto_id', 'ip')
    list_filter = ('acao', 'portal')
    search_fields = ('acao', 'objeto', 'objeto_id', 'usuario__username')
    readonly_fields = ('portal', 'usuario', 'acao', 'objeto', 'objeto_id', 'ip', 'detalhes', 'criado_em')
    date_hierarchy = 'criado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'email', 'telefone', 'status', 'criado_em')
    search_fields = ('nome', 'email')
    list_filter = ('status',)


@admin.register(Assinatura)
class AssinaturaAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('cliente', 'portal', 'plano', 'status', 'proximo_vencimento', 'atualizado_em')
    list_filter = ('status', 'plano')
    search_fields = ('cliente__email', 'portal__slug', 'kiwify_order_id', 'kiwify_subscription_id')
    autocomplete_fields = ('cliente', 'portal', 'plano')
    readonly_fields = ('criado_em', 'atualizado_em')


@admin.register(WebhookEvent)
class WebhookEventAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('criado_em', 'provedor', 'tipo', 'id_externo', 'status', 'processado', 'tentativas')
    list_filter = ('provedor', 'status', 'tipo')
    search_fields = ('id_externo', 'tipo')
    readonly_fields = (
        'provedor', 'tipo', 'id_externo', 'payload', 'status',
        'processado', 'erro', 'tentativas', 'criado_em', 'processado_em',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('criado_em', 'tipo', 'destinatario', 'status', 'tentativas', 'cliente')
    list_filter = ('tipo', 'status')
    search_fields = ('destinatario', 'assunto')
    readonly_fields = (
        'cliente', 'usuario', 'portal', 'tipo', 'destinatario', 'assunto',
        'status', 'erro', 'tentativas', 'enviado_em', 'criado_em', 'atualizado_em',
    )
    date_hierarchy = 'criado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
