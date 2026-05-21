from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Noticia, Categoria, Contribuicao, Anuncio, Perfil, Comentario, Curtida
from .utils_noticia import criar_noticia_de_contribuicao


class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    fields = ('tipo_conta', 'telefone', 'is_assinante', 'bio')


class UserAdmin(BaseUserAdmin):
    inlines = (PerfilInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ('noticia', 'usuario', 'texto_resumo', 'ativo', 'data_criacao')
    list_filter = ('ativo', 'data_criacao')
    search_fields = ('texto', 'usuario__username', 'noticia__titulo')
    list_editable = ('ativo',)

    def texto_resumo(self, obj):
        return obj.texto[:60] + ('...' if len(obj.texto) > 60 else '')
    texto_resumo.short_description = 'Comentário'


@admin.register(Curtida)
class CurtidaAdmin(admin.ModelAdmin):
    list_display = ('noticia', 'usuario', 'data_criacao')
    list_filter = ('data_criacao',)


@admin.register(Contribuicao)
class ContribuicaoAdmin(admin.ModelAdmin):
    """Onde você vê o que moradores e lojas enviaram — NÃO fica em Categorias."""
    list_display = (
        'status_badge', 'titulo', 'nome', 'tipo', 'categoria',
        'email', 'telefone', 'data_envio',
    )
    list_filter = ('status', 'tipo', 'categoria', 'data_envio')
    search_fields = ('titulo', 'conteudo', 'nome', 'email', 'telefone')
    readonly_fields = ('data_envio', 'preview_imagem', 'preview_video')
    list_per_page = 25
    actions = ['aprovar_publicacoes', 'rejeitar_publicacoes']
    fieldsets = (
        ('📥 Envio da comunidade', {
            'fields': (
                'status', 'titulo', 'conteudo', 'categoria', 'tipo',
                'imagem', 'video', 'preview_imagem', 'preview_video',
            ),
        }),
        ('Contato de quem enviou', {
            'fields': ('nome', 'email', 'telefone'),
        }),
        ('Sua análise', {
            'fields': ('observacao_admin', 'data_envio'),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.GET.get('status__exact') is None and 'change' not in request.path:
            return qs
        return qs

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        pendentes = Contribuicao.objects.filter(status='pendente').count()
        extra_context['subtitle'] = (
            f'⚠️ {pendentes} envio(s) aguardando sua análise — '
            'marque na lista e use a ação "Aprovar e publicar"'
        )
        return super().changelist_view(request, extra_context=extra_context)

    def status_badge(self, obj):
        cores = {
            'pendente': '#f59e0b',
            'aprovado': '#10b981',
            'rejeitado': '#ef4444',
        }
        cor = cores.get(obj.status, '#64748b')
        return format_html(
            '<span style="background:{};color:#fff;padding:4px 10px;border-radius:20px;'
            'font-size:11px;font-weight:700">{}</span>',
            cor,
            obj.get_status_display(),
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def preview_imagem(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" width="200" style="border-radius:8px"/>', obj.imagem.url)
        return '—'
    preview_imagem.short_description = 'Prévia da imagem'

    def preview_video(self, obj):
        if obj.video:
            return format_html(
                '<video src="{}" width="280" controls style="border-radius:8px"></video>',
                obj.video.url,
            )
        return '—'
    preview_video.short_description = 'Prévia do vídeo'

    @admin.action(description='✅ Aprovar e publicar no site')
    def aprovar_publicacoes(self, request, queryset):
        aprovadas = 0
        for contrib in queryset.filter(status='pendente'):
            criar_noticia_de_contribuicao(contrib)
            contrib.status = 'aprovado'
            contrib.save(update_fields=['status'])
            aprovadas += 1
        self.message_user(
            request,
            f'{aprovadas} envio(s) publicado(s) no portal Jiparaná.',
            messages.SUCCESS,
        )

    @admin.action(description='❌ Rejeitar envios selecionados')
    def rejeitar_publicacoes(self, request, queryset):
        count = queryset.filter(status='pendente').update(status='rejeitado')
        self.message_user(request, f'{count} envio(s) marcado(s) como não publicado.', messages.WARNING)


@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ('slot', 'titulo_interno', 'ativo', 'tem_preview')
    list_editable = ('ativo',)
    fieldsets = (
        (None, {
            'fields': ('slot', 'titulo_interno', 'ativo'),
            'description': (
                'O anúncio só aparece no site se estiver ATIVO e tiver código HTML ou imagem. '
                'Cada posição é única (topo, lateral ou artigo).'
            ),
        }),
        ('Conteúdo do anúncio', {
            'fields': ('codigo_html', 'imagem', 'link'),
        }),
    )

    def tem_preview(self, obj):
        return 'Sim' if obj.tem_conteudo else 'Vazio'
    tem_preview.short_description = 'Visível no site'


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'num_noticias')
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ('nome',)

    def num_noticias(self, obj):
        return obj.noticias.count()
    num_noticias.short_description = 'Notícias publicadas'


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'categoria', 'exclusivo_assinantes', 'destaque',
        'data_publicacao', 'visualizacoes', 'autor',
    )
    list_filter = ('categoria', 'exclusivo_assinantes', 'destaque', 'data_publicacao')
    fieldsets = (
        (None, {
            'fields': ('titulo', 'resumo', 'conteudo', 'categoria', 'autor', 'destaque', 'exclusivo_assinantes'),
        }),
        ('Mídia', {'fields': ('imagem', 'video')}),
        ('Estatísticas', {'fields': ('visualizacoes',)}),
    )
    search_fields = ('titulo', 'conteudo', 'resumo')
    list_editable = ('destaque',)
    date_hierarchy = 'data_publicacao'
    readonly_fields = ('visualizacoes',)

    def imagem_preview(self, obj):
        if obj.imagem:
            return format_html(
                '<img src="{}" width="80" style="object-fit:cover;border-radius:8px"/>',
                obj.imagem.url,
            )
        return '-'
    imagem_preview.short_description = 'Imagem'
