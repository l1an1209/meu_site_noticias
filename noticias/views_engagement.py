from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Noticia, Curtida, Comentario
from .forms import ComentarioForm


@login_required
@require_POST
def toggle_curtida(request, noticia_id):
    noticia = get_object_or_404(Noticia, pk=noticia_id)
    curtida = Curtida.objects.filter(usuario=request.user, noticia=noticia).first()
    if curtida:
        curtida.delete()
        curtiu = False
    else:
        Curtida.objects.create(usuario=request.user, noticia=noticia)
        curtiu = True
    total = noticia.curtidas.count()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'curtiu': curtiu, 'total': total})
    return redirect('detalhe', id=noticia_id)


@login_required
@require_POST
def adicionar_comentario(request, noticia_id):
    noticia = get_object_or_404(Noticia, pk=noticia_id)
    form = ComentarioForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.usuario = request.user
        comentario.noticia = noticia
        comentario.save()  # signal envia e-mail ao admin
        messages.success(request, 'Comentário publicado!')
    else:
        messages.error(request, 'Não foi possível publicar o comentário.')
    return redirect('detalhe', id=noticia_id)
