import json
from urllib.request import urlopen
from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.views import View


class ExperienciaView(TemplateView):
    """Página de animação: logo, localização, hora e clima."""
    template_name = 'noticias/experiencia.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cidade_lat'] = getattr(settings, 'SITE_LAT', -10.8854)
        ctx['cidade_lon'] = getattr(settings, 'SITE_LON', -61.9516)
        ctx['cidade_nome'] = settings.SITE_CITY
        return ctx


class ClimaApiView(View):
    """Proxy do clima (Open-Meteo, sem chave) para Ji-Paraná ou coordenadas do usuário."""

    def get(self, request):
        try:
            lat = float(request.GET.get('lat', getattr(settings, 'SITE_LAT', -10.8854)))
            lon = float(request.GET.get('lon', getattr(settings, 'SITE_LON', -61.9516)))
        except (TypeError, ValueError):
            lat, lon = -10.8854, -61.9516

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
                'cidade': settings.SITE_CITY,
            })
        except Exception as e:
            return JsonResponse({'ok': False, 'erro': str(e)}, status=502)
