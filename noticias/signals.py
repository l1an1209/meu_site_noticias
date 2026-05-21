from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.cache import cache
from .models import Anuncio, Contribuicao, Perfil, Comentario, Curtida
from .utils import limpar_cache_portal
from .services.email_notify import notificar_comentario, notificar_curtida, notificar_novo_envio


@receiver(post_save, sender=User)
def criar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.get_or_create(usuario=instance)


@receiver([post_save, post_delete], sender=Anuncio)
def limpar_cache_anuncio(sender, instance, **kwargs):
    cache_keys = [f'anuncio_{instance.slot}', 'anuncio_top', 'anuncio_sidebar', 'anuncio_article']
    cache.delete_many(cache_keys)


@receiver(post_save, sender=Contribuicao)
def limpar_nav_apos_envio(sender, instance, created, **kwargs):
    if instance.status == 'pendente':
        limpar_cache_portal()
    if created and instance.status == 'pendente':
        notificar_novo_envio(instance)


@receiver(post_save, sender=Comentario)
def email_novo_comentario(sender, instance, created, **kwargs):
    if created and instance.ativo:
        notificar_comentario(instance)


@receiver(post_save, sender=Curtida)
def email_nova_curtida(sender, instance, created, **kwargs):
    if created:
        notificar_curtida(instance)
