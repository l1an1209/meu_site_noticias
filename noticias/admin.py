from django.contrib import admin
from django.utils.html import format_html
from .models import Noticia, Categoria

# -----------------------------
# Admin Categoria
# -----------------------------
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'num_noticias')
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ('nome',)
    ordering = ('nome',)

    def num_noticias(self, obj):
        return obj.noticia_set.count()
    num_noticias.short_description = 'Número de notícias'

# -----------------------------
# Admin Noticia
# -----------------------------
@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria', 'data_publicacao', 'visualizacoes', 'autor_preview', 'imagem_preview')
    list_filter = ('categoria', 'data_publicacao')
    search_fields = ('titulo', 'conteudo')
    date_hierarchy = 'data_publicacao'
    readonly_fields = ('visualizacoes',)

    # Pré-visualizar autor (caso não tenha)
    def autor_preview(self, obj):
        return getattr(obj, 'autor', 'Redação')
    autor_preview.short_description = 'Autor'

    # Mini prévia da imagem
    def imagem_preview(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" width="100" style="object-fit: cover;"/>', obj.imagem.url)
        return "-"
    imagem_preview.short_description = 'Imagem'
