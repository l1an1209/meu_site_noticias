from django.http import Http404, HttpResponse
from django.views import View

from plataforma.services.publicidade import linha_ads_txt


class AdsTxtView(View):
    def get(self, request):
        if getattr(request, 'portal_from_compat_fallback', False):
            raise Http404()
        linha = linha_ads_txt(getattr(request, 'portal', None))
        if not linha:
            raise Http404()
        return HttpResponse(linha, content_type='text/plain; charset=utf-8')


class RobotsTxtView(View):
    def get(self, request):
        base = request.build_absolute_uri('/').rstrip('/')
        sitemap_url = base
        body = (
            'User-agent: *\n'
            'Allow: /\n'
            'Disallow: /admin/\n'
            'Disallow: /app/\n'
            'Disallow: /master/\n'
            'Disallow: /webhooks/\n'
            'Disallow: /painel/\n'
            'Disallow: /conta/\n'
            'Disallow: /entrar/\n'
            'Disallow: /cadastro/\n'
            'Disallow: /sair/\n'
            'Disallow: /senha/\n'
            f'Sitemap: {sitemap_url}/sitemap.xml\n'
        )
        return HttpResponse(body, content_type='text/plain')
