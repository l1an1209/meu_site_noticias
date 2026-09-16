import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Cria um superuser somente se DJANGO_SUPERUSER_USERNAME, '
        'DJANGO_SUPERUSER_EMAIL e DJANGO_SUPERUSER_PASSWORD estiverem definidos. '
        'Não altera usuário já existente.'
    )

    def handle(self, *args, **kwargs):
        username = (os.environ.get('DJANGO_SUPERUSER_USERNAME') or '').strip()
        email = (os.environ.get('DJANGO_SUPERUSER_EMAIL') or '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD') or ''

        if not username or not email or not password:
            raise CommandError(
                'Defina DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL e '
                'DJANGO_SUPERUSER_PASSWORD no ambiente. Nenhuma conta foi criada.'
            )

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING('SUPERUSER JÁ EXISTE!'))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS('SUPERUSER CRIADO!'))
