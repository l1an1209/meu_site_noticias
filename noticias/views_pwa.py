"""PWA por tenant: manifest, ícone e service worker no host do portal.

Usa o mesmo Host → Portal do middleware. Hosts de plataforma (sem tenant)
respondem 404. O service worker não cacheia páginas: só habilita instalação.
"""
from io import BytesIO

from django.http import Http404, HttpResponse, JsonResponse
from django.views import View
from PIL import Image, ImageDraw

from plataforma.resolvers import resolve_portal_from_host

SW_JS = """self.addEventListener('install', function (event) {
  self.skipWaiting();
});
self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', function (event) {
  event.respondWith(fetch(event.request));
});
"""


def _portal_do_host(request):
    return resolve_portal_from_host(request.get_host())


def _cor_rgba(hex_str):
    bruto = (hex_str or '#0d9488').strip().lstrip('#')
    if len(bruto) == 3:
        bruto = ''.join(c * 2 for c in bruto)
    if len(bruto) != 6:
        return (13, 148, 136, 255)
    try:
        return tuple(int(bruto[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    except ValueError:
        return (13, 148, 136, 255)


def _abrir_imagem_portal(portal):
    for campo in (portal.logo, portal.favicon, portal.imagem_compartilhamento):
        if not campo:
            continue
        try:
            campo.open('rb')
            img = Image.open(campo)
            img.load()
            return img.convert('RGBA')
        except Exception:
            continue
        finally:
            try:
                campo.close()
            except Exception:
                pass
    return None


def _png_icon(portal, size):
    fundo = _cor_rgba(portal.cor_primaria)
    tela = Image.new('RGBA', (size, size), fundo)
    origem = _abrir_imagem_portal(portal)
    if origem is None:
        letra = ((portal.nome or portal.cidade or 'N').strip() or 'N')[0].upper()
        draw = ImageDraw.Draw(tela)
        draw.text((size // 2, size // 2), letra, fill=(255, 255, 255, 255), anchor='mm')
        return tela
    origem.thumbnail((size, size), Image.Resampling.LANCZOS)
    x = (size - origem.width) // 2
    y = (size - origem.height) // 2
    tela.paste(origem, (x, y), origem)
    return tela


def _nome_curto(portal):
    texto = (portal.cidade or portal.nome or 'Portal').strip() or 'Portal'
    return texto[:12]


class ManifestView(View):
    def get(self, request):
        portal = _portal_do_host(request)
        if portal is None:
            raise Http404()
        origem = request.build_absolute_uri('/').rstrip('/')
        icon_192 = request.build_absolute_uri('/pwa/icon/192.png')
        icon_512 = request.build_absolute_uri('/pwa/icon/512.png')
        icones = [
            {
                'src': icon_192,
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_512,
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_192,
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'maskable',
            },
            {
                'src': icon_512,
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ]
        payload = {
            'id': origem + '/',
            'name': (portal.nome or 'Portal')[:45],
            'short_name': _nome_curto(portal),
            'description': (portal.seo_description_efetivo or portal.slogan or portal.nome or '')[:120],
            'start_url': '/',
            'scope': '/',
            'display': 'standalone',
            'orientation': 'portrait-primary',
            'lang': 'pt-BR',
            'theme_color': portal.cor_primaria or '#0d9488',
            'background_color': portal.cor_primaria or '#0d9488',
            'icons': icones,
        }
        resp = JsonResponse(payload)
        resp['Content-Type'] = 'application/manifest+json'
        resp['Cache-Control'] = 'no-cache'
        return resp


class PwaIconView(View):
    def get(self, request, size):
        portal = _portal_do_host(request)
        if portal is None:
            raise Http404()
        if size not in (192, 512):
            raise Http404()
        img = _png_icon(portal, size)
        buf = BytesIO()
        img.save(buf, format='PNG')
        resp = HttpResponse(buf.getvalue(), content_type='image/png')
        resp['Cache-Control'] = 'public, max-age=300'
        return resp


class ServiceWorkerView(View):
    def get(self, request):
        if _portal_do_host(request) is None:
            raise Http404()
        resp = HttpResponse(SW_JS, content_type='application/javascript; charset=utf-8')
        resp['Service-Worker-Allowed'] = '/'
        resp['Cache-Control'] = 'no-cache'
        return resp
