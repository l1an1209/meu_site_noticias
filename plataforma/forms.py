from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from noticias.image_utils import validate_image_file, validate_video_file
from noticias.models import Anuncio, Categoria, Noticia
from plataforma.models import Membership, Portal

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

    def __init__(self, *args, portal=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.portal = portal
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
