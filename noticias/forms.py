from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from .image_utils import (
    MAX_GALLERY_PHOTOS,
    validate_gallery_files,
    validate_image_file,
    validate_video_file,
)
from .models import Categoria, Comentario, Contribuicao, Perfil


class ContribuicaoForm(forms.ModelForm):
    class Meta:
        model = Contribuicao
        fields = [
            'titulo', 'conteudo', 'nome', 'email', 'telefone',
            'tipo', 'categoria', 'imagem', 'video',
        ]
        labels = {
            'titulo': 'Título da notícia ou promoção',
            'conteudo': 'Descreva com detalhes',
            'nome': 'Seu nome ou nome da loja',
            'email': 'E-mail para contato',
            'telefone': 'WhatsApp (opcional)',
            'tipo': 'Você é',
            'categoria': 'Categoria',
            'imagem': 'Foto principal (opcional)',
            'video': 'Vídeo (opcional)',
        }
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Ex.: Promoção na loja X, evento no bairro Y...',
            }),
            'conteudo': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': 'Conte o que está acontecendo na sua cidade...',
            }),
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome completo ou razão social',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'seu@email.com',
            }),
            'telefone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(00) 00000-0000',
            }),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'imagem': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/mp4,video/webm,video/quicktime',
            }),
        }

    def __init__(self, *args, extra_files=None, cidade='', portal=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_files = extra_files or []
        self.portal = portal
        self.fields['categoria'].required = True
        self.fields['categoria'].empty_label = 'Escolha a categoria'
        if portal is not None:
            self.fields['categoria'].queryset = Categoria.all_objects.filter(portal=portal)
        else:
            self.fields['categoria'].queryset = Categoria.objects.none()
        if cidade:
            self.fields['conteudo'].widget.attrs['placeholder'] = (
                f'Conte o que está acontecendo em {cidade}...'
            )

    def clean_categoria(self):
        categoria = self.cleaned_data.get('categoria')
        if categoria and self.portal and categoria.portal_id != self.portal.pk:
            raise forms.ValidationError('Categoria inválida para este portal.')
        return categoria

    def clean_imagem(self):
        return validate_image_file(self.cleaned_data.get('imagem'))

    def clean(self):
        cleaned = super().clean()
        try:
            validate_gallery_files(self.extra_files)
        except DjangoValidationError as exc:
            self.add_error(None, exc)
        total = len(self.extra_files) + (1 if cleaned.get('imagem') else 0)
        if total > MAX_GALLERY_PHOTOS:
            self.add_error(
                None,
                f'Envie no máximo {MAX_GALLERY_PHOTOS} fotos (principal + galeria).',
            )
        return cleaned

    def clean_video(self):
        return validate_video_file(self.cleaned_data.get('video'))


class CadastroForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control form-control-lg',
        'placeholder': 'seu@email.com',
        'autocomplete': 'email',
    }))
    tipo_conta = forms.ChoiceField(
        choices=Perfil.TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-lg'}),
        label='Tipo de conta',
    )
    telefone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '(00) 00000-0000',
        }),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Nome de usuário',
                'autocomplete': 'username',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'autocomplete': 'new-password',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'autocomplete': 'new-password',
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Perfil.objects.update_or_create(
                usuario=user,
                defaults={
                    'tipo_conta': self.cleaned_data['tipo_conta'],
                    'telefone': self.cleaned_data.get('telefone', ''),
                },
            )
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Usuário ou e-mail',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Senha',
            'autocomplete': 'current-password',
        })


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escreva seu comentário...',
                'maxlength': '1000',
            }),
        }
        labels = {'texto': ''}
