"""URL configuration for portal_noticias project."""
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from noticias.sitemaps import sitemaps
from noticias.views_seo import RobotsTxtView
from plataforma.views_vendas import PaginaCheckoutPlanoView, PaginaVendasView
from plataforma.views_webhooks import kiwify_webhook

urlpatterns = [
    path('admin/', admin.site.urls),
    path('webhooks/kiwify/', kiwify_webhook, name='webhook_kiwify'),
    path('comece/<slug:codigo>/', PaginaCheckoutPlanoView.as_view(), name='pagina_checkout_plano'),
    path('comece/', PaginaVendasView.as_view(), name='pagina_vendas'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', RobotsTxtView.as_view(), name='robots_txt'),
    path('app/', include('plataforma.urls')),
    path('master/', include('plataforma.urls_master')),
    path('', include('noticias.urls')),
]

handler400 = 'plataforma.views_errors.handler400'
handler403 = 'plataforma.views_errors.handler403'
handler404 = 'plataforma.views_errors.handler404'
handler500 = 'plataforma.views_errors.handler500'

if settings.DEBUG or getattr(settings, 'SERVE_MEDIA', False):
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
