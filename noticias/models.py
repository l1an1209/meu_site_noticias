from django.conf import settings
from django.db import models
from django.utils.text import slugify

class Categoria(models.Model):
    nome = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome

class Noticia(models.Model):
    titulo = models.CharField(max_length=200)
    conteudo = models.TextField()
    resumo = models.CharField(max_length=300, blank=True)
    autor = models.CharField(max_length=100, blank=True, default='Redação')
    data_publicacao = models.DateTimeField(auto_now_add=True)
    imagem = models.ImageField(upload_to='noticias/', blank=True, null=True)
    video = models.FileField(
        upload_to='noticias/videos/',
        blank=True,
        null=True,
        help_text='Vídeo da notícia (MP4, WebM).',
    )
    exclusivo_assinantes = models.BooleanField(
        default=False,
        help_text='Somente usuários assinantes / parceiros podem ver o conteúdo completo.',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='noticias',
    )
    visualizacoes = models.PositiveIntegerField(default=0)
    destaque = models.BooleanField(default=False)

    class Meta:
        ordering = ['-data_publicacao']

    def __str__(self):
        return self.titulo

    @property
    def resumo_curto(self):
        if self.resumo:
            return self.resumo
        words = self.conteudo.split()
        return ' '.join(words[:25]) + ('...' if len(words) > 25 else '')

    @property
    def total_curtidas(self):
        return self.curtidas.count()

    @property
    def total_comentarios(self):
        return self.comentarios.filter(ativo=True).count()

    @property
    def tem_video(self):
        return bool(self.video)


class Contribuicao(models.Model):
    TIPO_CHOICES = [
        ('cliente', 'Morador / Cliente'),
        ('loja', 'Loja / Comércio'),
        ('empresa', 'Empresa parceira'),
    ]
    STATUS_CHOICES = [
        ('pendente', 'Aguardando sua análise'),
        ('aprovado', 'Publicado no site'),
        ('rejeitado', 'Não publicado'),
    ]

    titulo = models.CharField(max_length=200, verbose_name='Título')
    conteudo = models.TextField(verbose_name='Texto completo')
    nome = models.CharField(max_length=100, verbose_name='Nome ou loja')
    email = models.EmailField(verbose_name='E-mail')
    telefone = models.CharField(max_length=20, blank=True, verbose_name='WhatsApp / telefone')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='cliente', verbose_name='Quem enviou')
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Categoria sugerida',
    )
    imagem = models.ImageField(upload_to='contribuicoes/', blank=True, null=True)
    video = models.FileField(
        upload_to='contribuicoes/videos/',
        blank=True,
        null=True,
        verbose_name='Vídeo (opcional)',
        help_text='MP4 ou WebM, até 50 MB.',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pendente',
        db_index=True,
    )
    data_envio = models.DateTimeField(auto_now_add=True, verbose_name='Data do envio')
    observacao_admin = models.TextField(blank=True, verbose_name='Sua observação (interna)')

    class Meta:
        ordering = ['-data_envio']
        verbose_name = 'Envio aguardando análise'
        verbose_name_plural = 'Envios da comunidade (analisar aqui)'

    def __str__(self):
        return f'{self.titulo} — {self.nome}'


class Anuncio(models.Model):
    """Anúncio exibido somente nos espaços reservados do layout."""
    SLOT_CHOICES = [
        ('top', 'Banner topo (abaixo do menu)'),
        ('sidebar', 'Barra lateral'),
        ('article', 'Dentro da notícia'),
    ]

    slot = models.CharField(max_length=20, choices=SLOT_CHOICES, unique=True, verbose_name='Posição')
    titulo_interno = models.CharField(max_length=100, verbose_name='Nome do anunciante')
    ativo = models.BooleanField(default=False, verbose_name='Exibir no site')
    codigo_html = models.TextField(
        blank=True,
        help_text='Cole aqui o código do Google AdSense ou HTML do parceiro.',
        verbose_name='Código HTML (AdSense)',
    )
    imagem = models.ImageField(upload_to='anuncios/', blank=True, null=True)
    link = models.URLField(blank=True, verbose_name='Link ao clicar na imagem')

    class Meta:
        verbose_name = 'Anúncio'
        verbose_name_plural = 'Anúncios (espaços reservados)'

    def __str__(self):
        return f'{self.get_slot_display()} — {self.titulo_interno}'

    @property
    def tem_conteudo(self):
        return self.ativo and (bool(self.codigo_html.strip()) or self.imagem)


class Perfil(models.Model):
    TIPO_CHOICES = [
        ('morador', 'Morador'),
        ('loja', 'Loja / Comércio'),
        ('assinante', 'Assinante / Parceiro'),
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil',
    )
    tipo_conta = models.CharField(max_length=20, choices=TIPO_CHOICES, default='morador')
    telefone = models.CharField(max_length=20, blank=True)
    is_assinante = models.BooleanField(
        default=False,
        help_text='Acesso a conteúdos exclusivos e parcerias fechadas.',
    )
    bio = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de usuário'
        verbose_name_plural = 'Perfis de usuários'

    def __str__(self):
        return self.usuario.get_username()

    @property
    def badge_label(self):
        if self.is_assinante:
            return 'Assinante'
        if self.tipo_conta == 'loja':
            return 'Loja parceira'
        return 'Morador'


class Comentario(models.Model):
    noticia = models.ForeignKey(Noticia, on_delete=models.CASCADE, related_name='comentarios')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comentarios',
    )
    texto = models.TextField(max_length=1000)
    ativo = models.BooleanField(default=True, help_text='Desmarque para ocultar no site')
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_criacao']
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'

    def __str__(self):
        return f'{self.usuario} em {self.noticia.titulo[:30]}'


class Curtida(models.Model):
    noticia = models.ForeignKey(Noticia, on_delete=models.CASCADE, related_name='curtidas')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='curtidas',
    )
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('noticia', 'usuario')
        verbose_name = 'Curtida'
        verbose_name_plural = 'Curtidas'

    def __str__(self):
        return f'{self.usuario} curtiu {self.noticia_id}'