import json
from urllib.request import urlopen
from urllib.parse import urlencode

from django.http import JsonResponse
from django.views.generic import TemplateView
from django.views import View


class ExperienciaView(TemplateView):
    """Página de animação: logo, localização, hora e clima."""
    template_name = 'noticias/experiencia.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        portal = getattr(self.request, 'portal', None)
        ctx['cidade_lat'] = portal.latitude if portal and portal.latitude is not None else 0
        ctx['cidade_lon'] = portal.longitude if portal and portal.longitude is not None else 0
        ctx['cidade_nome'] = portal.cidade if portal else ''
        return ctx


class ClimaApiView(View):
    """Proxy do clima (Open-Meteo) para as coordenadas do portal ou do usuário."""

    def get(self, request):
        portal = getattr(request, 'portal', None)
        default_lat = portal.latitude if portal and portal.latitude is not None else 0
        default_lon = portal.longitude if portal and portal.longitude is not None else 0
        try:
            lat = float(request.GET.get('lat', default_lat))
            lon = float(request.GET.get('lon', default_lon))
        except (TypeError, ValueError):
            lat, lon = default_lat, default_lon

        params = urlencode({
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,relative_humidity_2m,weather_code,apparent_temperature',
            'timezone': 'America/Porto_Velho',
        })
        url = f'https://api.open-meteo.com/v1/forecast?{params}'
        try:
            with urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            current = data.get('current', {})
            return JsonResponse({
                'ok': True,
                'temperatura': current.get('temperature_2m'),
                'sensacao': current.get('apparent_temperature'),
                'umidade': current.get('relative_humidity_2m'),
                'codigo': current.get('weather_code'),
                'cidade': portal.cidade if portal else '',
            })
        except Exception:
            return JsonResponse({'ok': False, 'erro': 'Clima indisponível no momento.'}, status=502)
