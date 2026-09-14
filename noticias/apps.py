from django.apps import AppConfig


class NoticiasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'noticias'
    verbose_name = 'Conteúdo do portal'

    def ready(self):
        import noticias.signals  # noqa: F401
        from django.contrib import admin
        from django.contrib.admin.sites import AdminSite

        admin.site.site_header = 'Plataforma de portais'
        admin.site.site_title = 'Plataforma'
        admin.site.index_title = 'Administração'

        original_get_app_list = AdminSite.get_app_list

        def get_app_list(self, request, app_label=None):
            app_list = original_get_app_list(self, request, app_label)
            for app in app_list:
                if app['app_label'] == 'noticias':
                    priority = {'Contribuicao': 0, 'Anuncio': 1, 'Noticia': 2, 'Categoria': 3}
                    app['models'].sort(
                        key=lambda m: priority.get(m['object_name'], 99)
                    )
            return app_list

        AdminSite.get_app_list = get_app_list
