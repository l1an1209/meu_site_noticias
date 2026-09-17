from uuid import uuid4

from django.utils.text import slugify

from plataforma.models import Portal
from plataforma.resolvers import PLATFORM_LABELS

SLUGS_RESERVADOS = PLATFORM_LABELS | {
    'app', 'master', 'api', 'webhooks', 'webhook', 'static', 'media',
    'admin', 'mail', 'ftp', 'ns', 'ns1', 'ns2', 'www', 'plataforma',
    'comece', 'planos', 'pricing', 'checkout', 'kiwify', 'suporte',
    'ajuda', 'status', 'cdn', 'assets',
}


def slug_disponivel(slug, ignore_pk=None):
    slug = (slug or '').strip().lower()
    if not slug or slug in SLUGS_RESERVADOS:
        return False
    qs = Portal.objects.filter(slug=slug)
    if ignore_pk:
        qs = qs.exclude(pk=ignore_pk)
    return not qs.exists()


def gerar_slug_provisorio():
    """Slug temporário de onboarding. Sem dados pessoais, produto ou plano."""
    for _ in range(20):
        slug = f'setup-{uuid4().hex[:8]}'
        if len(slug) <= 50 and slug_disponivel(slug):
            return slug
    return f'setup-{uuid4().hex}'[:50]


def gerar_slug_portal(nome, email=''):
    base = slugify(nome or '')[:50].strip('-')
    if not base:
        local = (email or 'portal').split('@')[0]
        base = slugify(local)[:50].strip('-') or 'portal'
    if base in SLUGS_RESERVADOS:
        base = f'portal-{base}'
    candidato = base
    n = 2
    while not slug_disponivel(candidato):
        candidato = f'{base}-{n}'[:60]
        n += 1
        if n > 50:
            from uuid import uuid4
            candidato = f'portal-{uuid4().hex[:8]}'
            break
    return candidato
