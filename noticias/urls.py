from django.urls import path
from .views import (
    NoticiaListView,
    NoticiaDetailView,
    NoticiaPorCategoriaListView,
)

urlpatterns = [
    path('', NoticiaListView.as_view(), name='index'),
    path('noticia/<int:id>/', NoticiaDetailView.as_view(), name='detalhe'),
    path('categoria/<slug:slug>/', NoticiaPorCategoriaListView.as_view(), name='noticias_por_categoria'),
]
