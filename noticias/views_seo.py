from django.conf import settings
from django.http import HttpResponse
from django.views import View


class RobotsTxtView(View):
    def get(self, request):
        base = request.build_absolute_uri('/').rstrip('/')
        sitemap_url = getattr(settings, 'SITE_URL', '') or base
        body = (
            'User-agent: *\n'
            'Allow: /\n'
            'Disallow: /admin/\n'
            'Disallow: /painel/\n'
            'Disallow: /conta/\n'
            'Disallow: /entrar/\n'
            'Disallow: /cadastro/\n'
            'Disallow: /sair/\n'
            f'Sitemap: {sitemap_url}/sitemap.xml\n'
        )
        return HttpResponse(body, content_type='text/plain')
