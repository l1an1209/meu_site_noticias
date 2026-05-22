from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Cria administrador automaticamente'

    def handle(self, *args, **kwargs):

        username = 'luanpatrick'
        email = 'luanpa082@gmail.com'
        password = 'L1an1010@'

        if not User.objects.filter(username=username).exists():

            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )

            self.stdout.write(
                self.style.SUCCESS('SUPERUSER CRIADO!')
            )

        else:
            self.stdout.write(
                self.style.WARNING('SUPERUSER JÁ EXISTE!')
            )