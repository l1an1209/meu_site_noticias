import json


def _rede_publicidade(portal, request):
    from plataforma.services.publicidade import payload_publicidade
    return payload_publicidade(portal, request)


def identidade_vazia():
    """Sem tenant: textos genéricos, nunca cidade/marca de um cliente."""
    return {
        'nav_categorias': [],
        'site_name': 'Portal de notícias',
        'site_name_short': '',
        'site_city': '',
        'site_state': '',
        'site_region': '',
        'site_slogan': '',
        'site_tagline': '',
        'site_description': '',
        'site_seo_title': 'Portal de notícias',
        'site_logo_url': '',
        'site_favicon_url': '',
        'site_og_image_url': '',
        'site_cor_primaria': '#0d9488',
        'site_cor_secundaria': '#1a365d',
        'site_cor_destaque': '#ea580c',
        'site_email': '',
        'site_telefone': '',
        'site_whatsapp': '',
        'site_whatsapp_link': '',
        'site_endereco': '',
        'site_facebook': '',
        'site_instagram': '',
        'site_youtube': '',
        'site_twitter': '',
        'site_tiktok': '',
        'site_adsense_client_id': '',
        'rede_publicidade': {
            'exibir': False, 'script': '', 'publisher_id': '', 'provedor': '', 'posicoes': [],
        },
        'site_texto_rodape': '',
        'site_json_ld': '',
        'envios_pendentes': 0,
        'user_is_assinante': False,
        'portal': None,
    }


def identidade_do_portal(portal, request=None):
    origin = ''
    if request is not None:
        origin = request.build_absolute_uri('/').rstrip('/')
    logo = portal.logo_url
    if logo and logo.startswith('/') and origin:
        logo_abs = origin + logo
    else:
        logo_abs = logo
    og = portal.og_image_url
    if og and og.startswith('/') and origin:
        og_abs = origin + og
    else:
        og_abs = og or logo_abs

    org = {
        '@context': 'https://schema.org',
        '@type': 'NewsMediaOrganization',
        'name': portal.nome,
        'url': origin or None,
        'description': portal.seo_description_efetivo or None,
        'address': {
            '@type': 'PostalAddress',
            'addressLocality': portal.cidade or None,
            'addressRegion': portal.estado or None,
            'addressCountry': 'BR',
        },
    }
    if logo_abs:
        org['logo'] = logo_abs
    if portal.email:
        org['email'] = portal.email
    if portal.telefone:
        org['telephone'] = portal.telefone
    same = [u for u in (portal.facebook, portal.instagram, portal.youtube, portal.twitter, portal.tiktok) if u]
    if same:
        org['sameAs'] = same

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if v not in (None, '', [])}
        return obj

    return {
        'site_name': portal.nome,
        'site_name_short': portal.cidade,
        'site_city': portal.cidade,
        'site_state': portal.estado,
        'site_region': portal.regiao or portal.cidade,
        'site_slogan': portal.slogan,
        'site_tagline': portal.tagline or portal.slogan,
        'site_description': portal.seo_description_efetivo,
        'site_seo_title': portal.seo_title_efetivo,
        'site_logo_url': logo,
        'site_favicon_url': portal.favicon_url or logo,
        'site_og_image_url': og or logo,
        'site_og_image_abs': og_abs,
        'site_cor_primaria': portal.cor_primaria or '#0d9488',
        'site_cor_secundaria': portal.cor_secundaria or '#1a365d',
        'site_cor_destaque': portal.cor_destaque or '#ea580c',
        'site_email': portal.email,
        'site_telefone': portal.telefone,
        'site_whatsapp': portal.whatsapp,
        'site_whatsapp_link': portal.whatsapp_link,
        'site_endereco': portal.endereco,
        'site_facebook': portal.facebook,
        'site_instagram': portal.instagram,
        'site_youtube': portal.youtube,
        'site_twitter': portal.twitter,
        'site_tiktok': portal.tiktok,
        'site_adsense_client_id': portal.adsense_client_id,
        'rede_publicidade': _rede_publicidade(portal, request),
        'site_texto_rodape': portal.texto_rodape,
        'site_json_ld': json.dumps(_clean(org), ensure_ascii=False),
        'portal': portal,
    }
