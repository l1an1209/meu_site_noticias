from .models import Membership


def is_platform_master(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def membership_for(user, portal):
    if not user or not user.is_authenticated or portal is None:
        return None
    return Membership.objects.filter(
        usuario=user, portal=portal, ativo=True,
    ).first()


def has_portal_role(request, *papeis):
    if is_platform_master(request.user):
        return True
    membership = getattr(request, 'membership', None)
    if membership is None or not membership.ativo:
        return False
    if not papeis:
        return True
    return membership.papel in papeis


PAPEIS_NOTICIA = {
    Membership.PAPEL_ADMIN,
    Membership.PAPEL_EDITOR,
    Membership.PAPEL_AUTOR,
}
PAPEIS_CATEGORIA = {
    Membership.PAPEL_ADMIN,
    Membership.PAPEL_EDITOR,
}
PAPEIS_ANUNCIO = {Membership.PAPEL_ADMIN}
PAPEIS_MODERACAO = {
    Membership.PAPEL_ADMIN,
    Membership.PAPEL_MODERADOR,
}


def papeis_para_model(model):
    name = model._meta.model_name
    mapping = {
        'noticia': PAPEIS_NOTICIA,
        'categoria': PAPEIS_CATEGORIA,
        'anuncio': PAPEIS_ANUNCIO,
        'contribuicao': PAPEIS_MODERACAO,
        'comentario': PAPEIS_MODERACAO,
        'curtida': PAPEIS_MODERACAO,
    }
    return mapping.get(name, {Membership.PAPEL_ADMIN})
