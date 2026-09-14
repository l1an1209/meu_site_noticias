from django.db import models

from .context import get_current_portal, is_request_bound


class TenantManager(models.Manager):
    """Em HTTP, restringe ao portal do contexto. Fora de request, não filtra (migrations/shell)."""

    def get_queryset(self):
        qs = super().get_queryset()
        if not is_request_bound():
            return qs
        portal = get_current_portal()
        if portal is None:
            return qs.none()
        return qs.filter(portal_id=portal.pk)

    def for_portal(self, portal):
        if portal is None:
            return super().get_queryset().none()
        return super().get_queryset().filter(portal_id=portal.pk)
