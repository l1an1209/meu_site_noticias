from django.core.exceptions import PermissionDenied
from django.contrib import admin

from .permissions import has_portal_role, is_platform_master, papeis_para_model


class TenantAdminMixin:
    """Isola o Django admin por portal. Superuser (master) vê todos."""

    def _qs_all(self):
        if hasattr(self.model, 'all_objects'):
            return self.model.all_objects.all()
        return super(admin.ModelAdmin, self).get_queryset(self.request)

    def get_queryset(self, request):
        self.request = request
        if hasattr(self.model, 'portal'):
            qs = self.model.all_objects.all()
            if is_platform_master(request.user):
                return qs
            portal = getattr(request, 'portal', None)
            if portal is None or not has_portal_role(request, *papeis_para_model(self.model)):
                return qs.none()
            return qs.filter(portal=portal)

        qs = super().get_queryset(request)
        portal = getattr(request, 'portal', None)
        if is_platform_master(request.user):
            return qs
        if portal is None:
            return qs.none()
        if hasattr(self.model, 'noticia'):
            return qs.filter(noticia__portal=portal)
        return qs.none()

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'portal_id'):
            if not obj.portal_id:
                if is_platform_master(request.user):
                    raise PermissionDenied('Selecione o portal do registro.')
                obj.portal = request.portal
            elif not is_platform_master(request.user):
                if request.portal is None or obj.portal_id != request.portal.pk:
                    raise PermissionDenied('Registro de outro portal.')
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        if is_platform_master(request.user):
            return True
        return has_portal_role(request, *papeis_para_model(self.model))

    def has_view_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def has_add_permission(self, request):
        if is_platform_master(request.user):
            return True
        return has_portal_role(request, *papeis_para_model(self.model))

    def has_change_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._object_allowed(request, obj)

    def _object_allowed(self, request, obj):
        if is_platform_master(request.user):
            return True
        if not has_portal_role(request, *papeis_para_model(self.model)):
            return False
        if obj is None:
            return True
        portal = getattr(request, 'portal', None)
        if portal is None:
            return False
        if hasattr(obj, 'portal_id'):
            return obj.portal_id == portal.pk
        noticia = getattr(obj, 'noticia', None)
        if noticia is not None:
            return noticia.portal_id == portal.pk
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'categoria':
            from noticias.models import Categoria
            portal = getattr(request, 'portal', None)
            if is_platform_master(request.user):
                kwargs['queryset'] = Categoria.all_objects.all()
            elif portal:
                kwargs['queryset'] = Categoria.all_objects.filter(portal=portal)
            else:
                kwargs['queryset'] = Categoria.all_objects.none()
        if db_field.name == 'portal' and not is_platform_master(request.user):
            from .models import Portal
            portal = getattr(request, 'portal', None)
            kwargs['queryset'] = (
                Portal.objects.filter(pk=portal.pk) if portal else Portal.objects.none()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not is_platform_master(request.user) and 'portal' not in readonly:
            if any(f.name == 'portal' for f in self.model._meta.fields):
                readonly.append('portal')
        return readonly


class SuperuserOnlyAdminMixin:
    def has_module_permission(self, request):
        return is_platform_master(request.user)

    def has_view_permission(self, request, obj=None):
        return is_platform_master(request.user)

    def has_add_permission(self, request):
        return is_platform_master(request.user)

    def has_change_permission(self, request, obj=None):
        return is_platform_master(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_platform_master(request.user)
