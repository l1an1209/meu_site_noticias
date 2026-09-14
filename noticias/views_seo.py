from django.http import HttpResponse
from django.views import View


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
