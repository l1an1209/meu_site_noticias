from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.text import slugify

from noticias.image_utils import (
    MAX_GALLERY_PHOTOS,
    validate_gallery_files,
    validate_image_file,
    validate_video_file,
)
from noticias.models import Anuncio, Categoria, Noticia
from plataforma.models import Membership, Portal
from plataforma.slugs import SLUGS_RESERVADOS, slug_disponivel

User = get_user_model()


class NoticiaForm(forms.ModelForm):
    class Meta:
        model = Noticia
        fields = [
            'titulo', 'resumo', 'conteudo', 'categoria', 'autor',
            'imagem', 'video', 'destaque', 'exclusivo_assinantes',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control cms-title', 'placeholder': 'Título da matéria'}),
            'resumo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Resumo para listagens e redes'}),
            'conteudo': forms.Textarea(attrs={'class': 'form-control cms-body', 'rows': 16, 'placeholder': 'Escreva a matéria…'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'autor': forms.TextInput(attrs={'class': 'form-control'}),
            'imagem': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'video': forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
            'destaque': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'exclusivo_assinantes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, portal=None, extra_files=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal = portal
        self.extra_files = extra_files or []
        if portal is not None:
            self.fields['categoria'].queryset = Categoria.all_objects.filter(portal=portal)
        else:
            self.fields['categoria'].queryset = Categoria.objects.none()

    def clean_categoria(self):
        categoria = self.cleaned_data.get('categoria')
        if categoria and self.portal and categoria.portal_id != self.portal.pk:
            raise forms.ValidationError('Categoria inválida para este portal.')
        return categoria

    def clean_imagem(self):
        return validate_image_file(self.cleaned_data.get('imagem'))

    def clean_video(self):
        return validate_video_file(self.cleaned_data.get('video'))

    def clean(self):
        cleaned = super().clean()
        try:
            validate_gallery_files(self.extra_files)
        except DjangoValidationError as exc:
            self.add_error(None, exc)
        extras = len(self.extra_files)
        capa = 1 if cleaned.get('imagem') or (self.instance.pk and self.instance.imagem) else 0
        atuais = self.instance.fotos.count() if self.instance.pk else 0
        if capa + atuais + extras > MAX_GALLERY_PHOTOS:
            self.add_error(
                None,
                f'Envie no máximo {MAX_GALLERY_PHOTOS} fotos (capa + galeria).',
            )
        return cleaned


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nome', 'slug']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'gerado automaticamente se vazio'}),
        }


class AnuncioForm(forms.ModelForm):
    class Meta:
        model = Anuncio
        fields = ['slot', 'titulo_interno', 'ativo', 'codigo_html', 'imagem', 'link']
        widgets = {
            'slot': forms.Select(attrs={'class': 'form-select'}),
            'titulo_interno': forms.TextInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'codigo_html': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'imagem': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'link': forms.URLInput(attrs={'class': 'form-control'}),
        }

    def clean_imagem(self):
        return validate_image_file(self.cleaned_data.get('imagem'))


class AparenciaForm(forms.ModelForm):
    class Meta:
        model = Portal
        fields = [
            'nome', 'cidade', 'estado', 'regiao', 'slogan', 'tagline', 'descricao',
            'logo', 'favicon', 'imagem_compartilhamento',
            'cor_primaria', 'cor_secundaria', 'cor_destaque',
            'email', 'telefone', 'whatsapp', 'endereco',
            'facebook', 'instagram', 'youtube', 'twitter', 'tiktok',
            'texto_rodape',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'cidade': forms.TextInput(attrs={'class': 'form-control'}),
            'estado': forms.TextInput(attrs={'class': 'form-control'}),
            'regiao': forms.TextInput(attrs={'class': 'form-control'}),
            'slogan': forms.TextInput(attrs={'class': 'form-control'}),
            'tagline': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'logo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'favicon': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'imagem_compartilhamento': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'cor_primaria': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'cor_secundaria': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'cor_destaque': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control'}),
            'endereco': forms.TextInput(attrs={'class': 'form-control'}),
            'facebook': forms.URLInput(attrs={'class': 'form-control'}),
            'instagram': forms.URLInput(attrs={'class': 'form-control'}),
            'youtube': forms.URLInput(attrs={'class': 'form-control'}),
            'twitter': forms.URLInput(attrs={'class': 'form-control'}),
            'tiktok': forms.URLInput(attrs={'class': 'form-control'}),
            'texto_rodape': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_logo(self):
        return validate_image_file(self.cleaned_data.get('logo'))

    def clean_favicon(self):
        from noticias.image_utils import validate_favicon_file
        return validate_favicon_file(self.cleaned_data.get('favicon'))

    def clean_imagem_compartilhamento(self):
        return validate_image_file(self.cleaned_data.get('imagem_compartilhamento'))


class SeoForm(forms.ModelForm):
    class Meta:
        model = Portal
        fields = ['seo_title', 'seo_description', 'imagem_compartilhamento', 'adsense_client_id']
        widgets = {
            'seo_title': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 70}),
            'seo_description': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 180}),
            'imagem_compartilhamento': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'adsense_client_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ca-pub-…'}),
        }

    def clean_imagem_compartilhamento(self):
        return validate_image_file(self.cleaned_data.get('imagem_compartilhamento'))


class ConfigForm(forms.ModelForm):
    class Meta:
        model = Portal
        fields = ['endereco', 'latitude', 'longitude', 'telefone', 'whatsapp', 'email']
        widgets = {
            'endereco': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class EquipeForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    papel = forms.ChoiceField(
        choices=Membership.PAPEL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Este usuário já existe. Use outro nome ou convide pelo admin.')
        return username

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('papel') not in dict(Membership.PAPEL_CHOICES):
            self.add_error('papel', 'Papel inválido.')
        return cleaned


class PortalOnboardingForm(forms.Form):
    nome = forms.CharField(
        label='Nome do portal',
        max_length=120,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Ex.: Jornal de Campinas',
            'autocomplete': 'organization',
        }),
    )
    slug = forms.CharField(
        label='Subdomínio',
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'jornaldecampinas',
            'autocomplete': 'off',
            'spellcheck': 'false',
        }),
    )

    def __init__(self, *args, portal=None, **kwargs):
        self.portal = portal
        super().__init__(*args, **kwargs)

    def clean_nome(self):
        nome = (self.cleaned_data.get('nome') or '').strip()
        if not nome:
            raise forms.ValidationError('Informe o nome do portal.')
        return nome

    def clean_slug(self):
        bruto = (self.cleaned_data.get('slug') or '').strip()
        slug = slugify(bruto)[:50].strip('-')
        if not slug:
            raise forms.ValidationError('Informe um subdomínio válido.')
        ignore_pk = self.portal.pk if self.portal is not None else None
        if slug in SLUGS_RESERVADOS:
            raise forms.ValidationError('Este subdomínio não está disponível.')
        if not slug_disponivel(slug, ignore_pk=ignore_pk):
            raise forms.ValidationError('Este subdomínio já está em uso. Escolha outro.')
        return slug
