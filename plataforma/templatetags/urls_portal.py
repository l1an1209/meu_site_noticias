from django import template

from plataforma.urls_portal import url_app_portal, url_publica_portal

register = template.Library()


@register.filter
def url_site_portal(portal):
    return url_publica_portal(portal)


@register.filter
def url_painel_portal(portal):
    return url_app_portal(portal)
