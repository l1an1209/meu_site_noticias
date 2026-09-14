"""Validação e otimização de imagens enviadas pelo portal."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
ALLOWED_MIME = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif',
    'image/pjpeg',
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_GALLERY_PHOTOS = 20
MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 82


def upload_path_noticia(instance, filename):
    return _safe_upload('noticias', filename)


def upload_path_galeria(instance, filename):
    return _safe_upload('noticias/galeria', filename)


def upload_path_contrib(instance, filename):
    return _safe_upload('contribuicoes', filename)


def upload_path_contrib_galeria(instance, filename):
    return _safe_upload('contribuicoes/galeria', filename)


def _safe_upload(folder, filename):
    ext = Path(filename or '').suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        ext = '.jpg'
    return f'{folder}/{uuid4().hex}{ext}'


def validate_image_file(uploaded, field_label='imagem'):
    if not uploaded:
        return uploaded
    name = getattr(uploaded, 'name', '') or ''
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValidationError(
            'Use JPG, PNG, WEBP ou GIF. O arquivo enviado não é uma imagem permitida.'
        )
    size = getattr(uploaded, 'size', None)
    if size and size > MAX_IMAGE_BYTES:
        raise ValidationError('Cada foto deve ter no máximo 8 MB.')
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type and content_type not in ALLOWED_MIME:
        raise ValidationError('Tipo de arquivo inválido. Envie apenas imagens.')
    try:
        uploaded.seek(0)
        with Image.open(uploaded) as img:
            img.verify()
        uploaded.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError('Não foi possível ler esta imagem. Envie outro arquivo.')
    return uploaded


def validate_gallery_files(files):
    files = [f for f in files if f]
    if len(files) > MAX_GALLERY_PHOTOS:
        raise ValidationError(f'Envie no máximo {MAX_GALLERY_PHOTOS} fotos por vez.')
    for uploaded in files:
        validate_image_file(uploaded)
    return files


def optimize_image_field(image_field):
    """Redimensiona e comprime uma ImageField recém-enviada. Retorna True se alterou."""
    if not image_field:
        return False
    try:
        image_field.open('rb')
        img = Image.open(image_field)
        img.load()
    except (UnidentifiedImageError, OSError, ValueError, FileNotFoundError):
        return False

    fmt = (img.format or 'JPEG').upper()
    if fmt == 'GIF':
        image_field.seek(0)
        return False

    changed = False
    w, h = img.size
    if w > MAX_IMAGE_SIDE or h > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        changed = True

    buffer = BytesIO()
    name = Path(getattr(image_field, 'name', 'foto.jpg')).name
    if fmt == 'PNG' and img.mode in ('RGBA', 'LA', 'P'):
        if img.mode == 'P':
            img = img.convert('RGBA')
        img.save(buffer, format='PNG', optimize=True)
        ext = '.png'
    elif fmt == 'WEBP':
        img.save(buffer, format='WEBP', quality=JPEG_QUALITY, method=4)
        ext = '.webp'
    else:
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        ext = '.jpg'
        changed = True

    if not changed and buffer.tell() >= getattr(image_field, 'size', 0):
        image_field.seek(0)
        return False

    buffer.seek(0)
    stem = Path(name).stem[:40] or 'foto'
    image_field.save(f'{stem}{ext}', ContentFile(buffer.read()), save=False)
    return True


def is_new_upload(file_field):
    if not file_field:
        return False
    return isinstance(getattr(file_field, 'file', None), UploadedFile) or not getattr(
        file_field, '_committed', True
    )
