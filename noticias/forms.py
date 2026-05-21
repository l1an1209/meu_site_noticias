from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Contribuicao, Comentario, Perfil


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
            'imagem': 'Foto (opcional)',
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
                'placeholder': 'Conte o que está acontecendo em Jiparaná...',
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
                'placeholder': '(69) 99999-9999',
            }),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'imagem': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/mp4,video/webm,video/quicktime',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].required = True
        self.fields['categoria'].empty_label = 'Escolha a categoria'

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video and video.size > 50 * 1024 * 1024:
            raise forms.ValidationError('O vídeo deve ter no máximo 50 MB.')
        return video


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
            'placeholder': '(69) 99999-9999',
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
