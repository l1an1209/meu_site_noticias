from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        username = "luan"
        password = "l1an1010@"
        email = "luanpa082@gmail.com"

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )

            self.stdout.write("SUPERUSER CRIADO")
        else:
            u = User.objects.get(username=username)
            u.is_staff = True
            u.is_superuser = True
            u.save()

            self.stdout.write("SUPERUSER ATUALIZADO")