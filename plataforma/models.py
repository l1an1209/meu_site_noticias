from pathlib import Path
import uuid

from django.conf import settings
from django.db import models

from plataforma.managers import TenantManager


def _portal_asset_path(instance, filename, pasta):
    ext = Path(filename or '').suffix.lower() or '.png'
    if ext not in {'.png', '.jpg', '.jpeg', '.webp', '.ico', '.gif'}:
        ext = '.png'
    return f'portais/{instance.slug}/{pasta}{ext}'


def upload_portal_logo(instance, filename):
    return _portal_asset_path(instance, filename, 'logo')


def upload_portal_favicon(instance, filename):
    return _portal_asset_path(instance, filename, 'favicon')


def upload_portal_og(instance, filename):
    return _portal_asset_path(instance, filename, 'og')


class Plano(models.Model):
    codigo = models.SlugField(unique=True)
    nome = models.CharField(max_length=80)
    descricao = models.TextField(blank=True)
    recursos = models.TextField(
        blank=True,
        help_text='Um recurso por linha, exibido na página de venda.',
    )
    preco_mensal = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text='Preço em reais. 0 = cortesia / legado.',
    )
    max_storage_mb = models.PositiveIntegerField(default=1024)
    max_usuarios = models.PositiveIntegerField(default=5)
    max_noticias_mes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Vazio = sem limite mensal.',
    )
    kiwify_product_id = models.CharField(
        max_length=80,
        blank=True,
        db_index=True,
        help_text='Product.product_id na Kiwify.',
    )
    kiwify_plan_id = models.CharField(
        max_length=80,
        blank=True,
        db_index=True,
        help_text='Subscription.plan.id na Kiwify.',
    )
    checkout_url = models.URLField(
        blank=True,
        help_text='Link de checkout Kiwify deste plano.',
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordem', 'preco_mensal', 'nome']
        verbose_name = 'Plano'
        verbose_name_plural = 'Planos'

    def __str__(self):
        return self.nome

    def lista_recursos(self):
        return [linha.strip() for linha in (self.recursos or '').splitlines() if linha.strip()]

    @property
    def e_gratuito(self):
        return self.preco_mensal == 0


class Portal(models.Model):
    STATUS_ATIVO = 'ativo'
    STATUS_INATIVO = 'inativo'
    STATUS_BLOQUEADO = 'bloqueado'
    STATUS_CHOICES = [
        (STATUS_ATIVO, 'Ativo'),
        (STATUS_INATIVO, 'Inativo'),
        (STATUS_BLOQUEADO, 'Bloqueado'),
    ]

    PAGAMENTO_CORTESIA = 'cortesia'
    PAGAMENTO_GRATUITO = 'gratuito'
    PAGAMENTO_PAGO = 'pago'
    PAGAMENTO_PENDENTE = 'pendente'
    PAGAMENTO_ATRASADO = 'atrasado'
    PAGAMENTO_CHOICES = [
        (PAGAMENTO_CORTESIA, 'Cortesia / legado'),
        (PAGAMENTO_GRATUITO, 'Gratuito'),
        (PAGAMENTO_PAGO, 'Pago'),
        (PAGAMENTO_PENDENTE, 'Pendente'),
        (PAGAMENTO_ATRASADO, 'Atrasado'),
    ]

    PUBLICIDADE_HERDAR = ''
    PUBLICIDADE_ATIVA = 'ativa'
    PUBLICIDADE_INATIVA = 'inativa'
    PUBLICIDADE_MODO_CHOICES = [
        (PUBLICIDADE_HERDAR, 'Seguir a política do plano'),
        (PUBLICIDADE_ATIVA, 'Exibir publicidade'),
        (PUBLICIDADE_INATIVA, 'Não exibir publicidade'),
    ]

    SLUG_LEGADO = 'noticiasjiparana'
    SLUG_TESTE = 'portalbeta'

    nome = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, help_text='Subdomínio: {slug}.plataforma.com.br')
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text='Domínio próprio futuro, ex.: www.noticiascliente.com.br',
    )
    cidade = models.CharField(max_length=80)
    estado = models.CharField(max_length=50, help_text='UF ou nome do estado')
    regiao = models.CharField(max_length=120, blank=True)
    slogan = models.CharField(max_length=160, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    descricao = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    twitter = models.URLField(blank=True, verbose_name='X / Twitter')
    tiktok = models.URLField(blank=True)
    logo = models.ImageField(upload_to=upload_portal_logo, blank=True, null=True)
    favicon = models.ImageField(upload_to=upload_portal_favicon, blank=True, null=True)
    imagem_compartilhamento = models.ImageField(
        upload_to=upload_portal_og,
        blank=True,
        null=True,
        help_text='Imagem Open Graph / compartilhamento.',
    )
    cor_primaria = models.CharField(max_length=7, default='#0d9488')
    cor_secundaria = models.CharField(max_length=7, default='#1a365d')
    cor_destaque = models.CharField(max_length=7, default='#ea580c')
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=180, blank=True)
    adsense_client_id = models.CharField(
        max_length=40,
        blank=True,
        help_text='Ex.: ca-pub-123. Vazio = não carrega o script do AdSense.',
    )
    texto_rodape = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portais',
    )
    plano = models.ForeignKey(
        Plano,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portais',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ATIVO,
        db_index=True,
    )
    pagamento_status = models.CharField(
        max_length=20,
        choices=PAGAMENTO_CHOICES,
        default=PAGAMENTO_CORTESIA,
    )
    publicidade_modo = models.CharField(
        max_length=16,
        choices=PUBLICIDADE_MODO_CHOICES,
        default=PUBLICIDADE_HERDAR,
        blank=True,
        help_text='Vazio segue a política global do plano. O Master pode ligar ou desligar neste portal.',
    )
    cliente_nome = models.CharField(max_length=120, blank=True)
    cliente_email = models.EmailField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_acesso_em = models.DateTimeField(null=True, blank=True)
    setup_concluido = models.BooleanField(
        default=False,
        help_text='False = portal novo ainda sem nome/slug definitivos (wizard futuro). '
                  'Portais já existentes na migration ficam True.',
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Portal'
        verbose_name_plural = 'Portais'
        indexes = [
            models.Index(fields=['status', 'slug']),
        ]

    def __str__(self):
        return f'{self.nome} ({self.slug})'

    @classmethod
    def get_default(cls):
        portal = cls.objects.filter(slug=cls.SLUG_LEGADO).first()
        if portal:
            return portal
        return cls.objects.order_by('id').first()

    @property
    def seo_title_efetivo(self):
        if self.seo_title:
            return self.seo_title
        if self.slogan:
            return f'{self.nome} — {self.slogan}'
        return self.nome

    @property
    def seo_description_efetivo(self):
        return self.seo_description or self.descricao or self.tagline or self.slogan

    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        return ''

    @property
    def favicon_url(self):
        if self.favicon:
            return self.favicon.url
        return self.logo_url

    @property
    def og_image_url(self):
        if self.imagem_compartilhamento:
            return self.imagem_compartilhamento.url
        return self.logo_url

    @property
    def whatsapp_link(self):
        digits = ''.join(c for c in (self.whatsapp or '') if c.isdigit())
        if not digits:
            return ''
        return f'https://wa.me/{digits}'

    @property
    def host_previsto(self):
        base = getattr(settings, 'TENANT_BASE_DOMAIN', 'plataforma.com.br')
        return f'{self.slug}.{base}'

    def assinatura_atual(self):
        from django.core.exceptions import ObjectDoesNotExist
        try:
            return self.assinatura
        except ObjectDoesNotExist:
            return None

    @property
    def should_show_ads(self):
        from plataforma.services.publicidade import portal_deve_exibir_publicidade
        return portal_deve_exibir_publicidade(self)


class Membership(models.Model):
    PAPEL_ADMIN = 'admin'
    PAPEL_EDITOR = 'editor'
    PAPEL_AUTOR = 'autor'
    PAPEL_MODERADOR = 'moderador'
    PAPEL_CHOICES = [
        (PAPEL_ADMIN, 'Administrador'),
        (PAPEL_EDITOR, 'Editor'),
        (PAPEL_AUTOR, 'Autor / redator'),
        (PAPEL_MODERADOR, 'Moderador'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    portal = models.ForeignKey(
        Portal,
        on_delete=models.CASCADE,
        related_name='membros',
    )
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES, default=PAPEL_ADMIN)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Equipe do portal'
        verbose_name_plural = 'Equipes dos portais'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'portal'],
                name='uniq_membership_usuario_portal',
            ),
        ]

    def __str__(self):
        return f'{self.usuario} @ {self.portal.slug} ({self.papel})'


class AuditLog(models.Model):
    portal = models.ForeignKey(
        Portal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auditoria',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auditoria',
    )
    acao = models.CharField(max_length=80, db_index=True)
    objeto = models.CharField(max_length=120, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    detalhes = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Registro de auditoria'
        verbose_name_plural = 'Auditoria'

    def __str__(self):
        return f'{self.acao} {self.objeto}#{self.objeto_id}'


class Cliente(models.Model):
    STATUS_ATIVO = 'ativo'
    STATUS_INATIVO = 'inativo'
    STATUS_CHOICES = [
        (STATUS_ATIVO, 'Ativo'),
        (STATUS_INATIVO, 'Inativo'),
    ]

    nome = models.CharField(max_length=160)
    email = models.EmailField(unique=True)
    telefone = models.CharField(max_length=30, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ATIVO,
        db_index=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return f'{self.nome} <{self.email}>'


class Assinatura(models.Model):
    STATUS_AGUARDANDO = 'aguardando_pagamento'
    STATUS_ATIVA = 'ativa'
    STATUS_PENDENTE = 'pagamento_pendente'
    STATUS_ATRASADA = 'atrasada'
    STATUS_CANCELADA = 'cancelada'
    STATUS_BLOQUEADA = 'bloqueada'
    ORIGEM_KIWIFY = 'kiwify'
    ORIGEM_GRATUITA = 'gratuito'
    ORIGEM_CHOICES = [
        (ORIGEM_KIWIFY, 'Kiwify'),
        (ORIGEM_GRATUITA, 'Gratuito'),
    ]
    STATUS_CHOICES = [
        (STATUS_AGUARDANDO, 'Aguardando pagamento'),
        (STATUS_ATIVA, 'Ativa'),
        (STATUS_PENDENTE, 'Pagamento pendente'),
        (STATUS_ATRASADA, 'Atrasada'),
        (STATUS_CANCELADA, 'Cancelada'),
        (STATUS_BLOQUEADA, 'Bloqueada'),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='assinaturas',
    )
    portal = models.OneToOneField(
        Portal,
        on_delete=models.PROTECT,
        related_name='assinatura',
    )
    plano = models.ForeignKey(
        Plano,
        on_delete=models.PROTECT,
        related_name='assinaturas',
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_AGUARDANDO,
        db_index=True,
    )
    origem = models.CharField(
        max_length=20,
        choices=ORIGEM_CHOICES,
        default=ORIGEM_KIWIFY,
        db_index=True,
    )
    kiwify_subscription_id = models.CharField(max_length=80, blank=True, db_index=True)
    kiwify_order_id = models.CharField(max_length=80, blank=True, db_index=True)
    kiwify_transaction_id = models.CharField(max_length=80, blank=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    proximo_vencimento = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    bloqueado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Assinatura'
        verbose_name_plural = 'Assinaturas'
        constraints = [
            models.UniqueConstraint(
                fields=['kiwify_order_id'],
                condition=~models.Q(kiwify_order_id=''),
                name='uniq_assinatura_kiwify_order',
            ),
            models.UniqueConstraint(
                fields=['kiwify_subscription_id'],
                condition=~models.Q(kiwify_subscription_id=''),
                name='uniq_assinatura_kiwify_sub',
            ),
        ]

    def __str__(self):
        return f'{self.cliente.email} · {self.portal.slug} · {self.status}'

    @property
    def e_gratuita(self):
        return self.origem == self.ORIGEM_GRATUITA or (
            self.plano_id and self.plano.preco_mensal == 0
        )


class ConfiguracaoMonetizacao(models.Model):
    """Política global de publicidade da rede. Uma única linha, só o Master altera."""

    PROVEDOR_ADSENSE = 'adsense'
    PROVEDOR_OUTRO = 'outro'
    PROVEDOR_PROPRIA = 'propria'
    PROVEDOR_CHOICES = [
        (PROVEDOR_ADSENSE, 'AdSense'),
        (PROVEDOR_OUTRO, 'Outro'),
        (PROVEDOR_PROPRIA, 'Própria'),
    ]
    POSICOES = ('top', 'sidebar', 'article', 'feed', 'mobile')

    ativa = models.BooleanField(default=False)
    provedor = models.CharField(
        max_length=20, choices=PROVEDOR_CHOICES, default=PROVEDOR_ADSENSE,
    )
    publisher_id = models.CharField(
        max_length=40, blank=True, help_text='Ex.: ca-pub-123. Usado no script único do AdSense.',
    )
    codigo_script = models.TextField(
        blank=True,
        help_text='Script ou HTML do provedor. Carregado uma vez por página pública.',
    )
    posicoes = models.JSONField(
        default=list,
        blank=True,
        help_text='Posições permitidas: top, sidebar, article, feed, mobile.',
    )
    publicidade_gratuito = models.BooleanField(
        default=True,
        help_text='Portais de plano gratuito herdam esta política.',
    )
    publicidade_pago = models.BooleanField(
        default=False,
        help_text='Portais de plano pago herdam esta política.',
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de monetização'
        verbose_name_plural = 'Configuração de monetização'

    def __str__(self):
        return 'Monetização da rede'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={'posicoes': ['top', 'article']},
        )
        return obj

    def posicoes_permitidas(self):
        brutas = self.posicoes or []
        if isinstance(brutas, str):
            brutas = [p.strip() for p in brutas.split(',') if p.strip()]
        return [p for p in brutas if p in self.POSICOES]


class WebhookEvent(models.Model):
    STATUS_RECEBIDO = 'recebido'
    STATUS_PROCESSADO = 'processado'
    STATUS_IGNORADO = 'ignorado'
    STATUS_ERRO = 'erro'
    STATUS_CHOICES = [
        (STATUS_RECEBIDO, 'Recebido'),
        (STATUS_PROCESSADO, 'Processado'),
        (STATUS_IGNORADO, 'Ignorado'),
        (STATUS_ERRO, 'Erro'),
    ]

    provedor = models.CharField(max_length=40, default='kiwify', db_index=True)
    tipo = models.CharField(max_length=80, db_index=True)
    id_externo = models.CharField(max_length=120, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEBIDO)
    processado = models.BooleanField(default=False)
    erro = models.TextField(blank=True)
    tentativas = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    processado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Evento de webhook'
        verbose_name_plural = 'Eventos de webhook'
        constraints = [
            models.UniqueConstraint(
                fields=['provedor', 'tipo', 'id_externo'],
                name='uniq_webhook_provedor_tipo_id',
            ),
        ]

    def __str__(self):
        return f'{self.provedor}:{self.tipo}:{self.id_externo}'

    def order_id_publico(self):
        return str((self.payload or {}).get('order_id') or self.id_externo)

    def subscription_id_publico(self):
        sub = (self.payload or {}).get('Subscription') or {}
        if isinstance(sub, dict):
            return str(sub.get('id') or '')
        return ''


class EmailLog(models.Model):
    STATUS_PENDENTE = 'pendente'
    STATUS_ENVIADO = 'enviado'
    STATUS_FALHOU = 'falhou'
    STATUS_NAO_CONFIGURADO = 'nao_configurado'
    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_ENVIADO, 'Enviado'),
        (STATUS_FALHOU, 'Falhou'),
        (STATUS_NAO_CONFIGURADO, 'Não configurado'),
    ]

    TIPO_ONBOARDING = 'onboarding'
    TIPO_RECUPERACAO = 'recuperacao_senha'
    TIPO_TESTE = 'teste_smtp'
    TIPO_REENVIO = 'reenvio_acesso'
    TIPO_ADMIN = 'notificacao_admin'
    TIPO_CHOICES = [
        (TIPO_ONBOARDING, 'Onboarding'),
        (TIPO_RECUPERACAO, 'Recuperação de senha'),
        (TIPO_TESTE, 'Teste SMTP'),
        (TIPO_REENVIO, 'Reenvio de acesso'),
        (TIPO_ADMIN, 'Notificação administrativa'),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='emails',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='emails_plataforma',
    )
    portal = models.ForeignKey(
        Portal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='emails',
    )
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, db_index=True)
    destinatario = models.EmailField(db_index=True)
    assunto = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDENTE, db_index=True,
    )
    erro = models.TextField(blank=True)
    tentativas = models.PositiveIntegerField(default=1)
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Log de e-mail'
        verbose_name_plural = 'Logs de e-mail'
        indexes = [
            models.Index(fields=['destinatario', 'status']),
            models.Index(fields=['tipo', 'status']),
        ]

    def __str__(self):
        return f'{self.tipo} → {self.destinatario} ({self.status})'


class AnalyticsSession(models.Model):
    DISPOSITIVO_DESCONHECIDO = 'unknown'
    DISPOSITIVO_MOBILE = 'mobile'
    DISPOSITIVO_TABLET = 'tablet'
    DISPOSITIVO_DESKTOP = 'desktop'
    DISPOSITIVO_CHOICES = [
        (DISPOSITIVO_DESCONHECIDO, 'Desconhecido'),
        (DISPOSITIVO_MOBILE, 'Mobile'),
        (DISPOSITIVO_TABLET, 'Tablet'),
        (DISPOSITIVO_DESKTOP, 'Desktop'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rotulo = models.CharField(max_length=8, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    visto_em = models.DateTimeField(db_index=True)
    path_primeiro = models.CharField(max_length=200, blank=True)
    path_atual = models.CharField(max_length=200, blank=True)
    referrer = models.CharField(max_length=300, blank=True)
    utm_source = models.CharField(max_length=80, blank=True)
    utm_medium = models.CharField(max_length=80, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    utm_term = models.CharField(max_length=120, blank=True)
    fbclid = models.CharField(max_length=200, blank=True)
    fbp = models.CharField(max_length=80, blank=True)
    fbc = models.CharField(max_length=200, blank=True)
    dispositivo = models.CharField(
        max_length=16, choices=DISPOSITIVO_CHOICES, default=DISPOSITIVO_DESCONHECIDO,
    )
    portal = models.ForeignKey(
        Portal, on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics_sessoes',
    )

    class Meta:
        ordering = ['-visto_em']
        verbose_name = 'Sessão de analytics'
        verbose_name_plural = 'Sessões de analytics'
        indexes = [
            models.Index(fields=['visto_em']),
            models.Index(fields=['portal', 'visto_em']),
        ]

    def __str__(self):
        return self.rotulo

    def origem_label(self):
        fonte = (self.utm_source or '').lower()
        meio = (self.utm_medium or '').lower()
        if fonte in {'fb', 'facebook', 'ig', 'instagram', 'meta'} or self.fbclid or meio == 'paid':
            if 'instagram' in fonte or fonte == 'ig':
                return 'Instagram'
            return 'Meta Ads'
        if 'google' in fonte or meio == 'organic':
            return 'Google'
        if fonte:
            return self.utm_source[:40]
        if self.referrer:
            return 'Referência'
        return 'Direto'


class AnalyticsEvent(models.Model):
    sessao = models.ForeignKey(
        AnalyticsSession, on_delete=models.CASCADE, related_name='eventos',
    )
    portal = models.ForeignKey(
        Portal, on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics_eventos',
    )
    tipo = models.CharField(max_length=40, db_index=True)
    path = models.CharField(max_length=200, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    ref_externo = models.CharField(max_length=80, blank=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['criado_em']
        verbose_name = 'Evento de analytics'
        verbose_name_plural = 'Eventos de analytics'
        indexes = [
            models.Index(fields=['tipo', 'criado_em']),
            models.Index(fields=['sessao', 'criado_em']),
            models.Index(fields=['portal', 'tipo', 'criado_em']),
            models.Index(fields=['tipo', 'ref_externo']),
        ]

    def __str__(self):
        return f'{self.tipo} {self.path}'


class ConversaAjuda(models.Model):
    TIPO_DUVIDA = 'duvida'
    TIPO_PROBLEMA = 'problema'
    TIPO_SUGESTAO = 'sugestao'
    TIPO_CHOICES = [
        (TIPO_DUVIDA, 'Dúvida'),
        (TIPO_PROBLEMA, 'Problema'),
        (TIPO_SUGESTAO, 'Sugestão'),
    ]

    STATUS_ABERTA = 'aberta'
    STATUS_AGUARDANDO_CLIENTE = 'aguardando_cliente'
    STATUS_AGUARDANDO_SUPORTE = 'aguardando_suporte'
    STATUS_ENCERRADA = 'encerrada'
    STATUS_CHOICES = [
        (STATUS_ABERTA, 'Aberta'),
        (STATUS_AGUARDANDO_CLIENTE, 'Aguardando cliente'),
        (STATUS_AGUARDANDO_SUPORTE, 'Aguardando suporte'),
        (STATUS_ENCERRADA, 'Encerrada'),
    ]

    portal = models.ForeignKey(
        Portal,
        on_delete=models.CASCADE,
        related_name='conversas_ajuda',
        db_index=True,
    )
    aberto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversas_ajuda_abertas',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_DUVIDA)
    assunto = models.CharField(max_length=140)
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_AGUARDANDO_SUPORTE,
        db_index=True,
    )
    ultima_mensagem = models.CharField(max_length=180, blank=True)
    nao_lidas_cliente = models.PositiveIntegerField(default=0)
    nao_lidas_master = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-atualizado_em']
        verbose_name = 'Conversa de ajuda'
        verbose_name_plural = 'Conversas de ajuda'
        indexes = [
            models.Index(fields=['portal', '-atualizado_em']),
            models.Index(fields=['status', '-atualizado_em']),
        ]

    def __str__(self):
        return f'{self.assunto} ({self.portal_id})'

    def adicionar_mensagem(self, autor, origem, texto):
        texto = (texto or '').strip()[:4000]
        if not texto:
            raise ValueError('Mensagem vazia.')
        msg = MensagemAjuda.objects.create(
            conversa=self,
            autor=autor if getattr(autor, 'is_authenticated', False) else None,
            origem=origem,
            texto=texto,
        )
        self.ultima_mensagem = texto[:180]
        if origem == MensagemAjuda.ORIGEM_CLIENTE:
            self.nao_lidas_master = (self.nao_lidas_master or 0) + 1
            self.status = self.STATUS_AGUARDANDO_SUPORTE
            self.encerrado_em = None
        else:
            self.nao_lidas_cliente = (self.nao_lidas_cliente or 0) + 1
            if self.status != self.STATUS_ENCERRADA:
                self.status = self.STATUS_AGUARDANDO_CLIENTE
        self.save(update_fields=[
            'ultima_mensagem', 'nao_lidas_cliente', 'nao_lidas_master',
            'status', 'encerrado_em', 'atualizado_em',
        ])
        return msg

    def marcar_lida_cliente(self):
        if self.nao_lidas_cliente:
            self.nao_lidas_cliente = 0
            self.save(update_fields=['nao_lidas_cliente', 'atualizado_em'])

    def marcar_lida_master(self):
        if self.nao_lidas_master:
            self.nao_lidas_master = 0
            self.save(update_fields=['nao_lidas_master', 'atualizado_em'])

    def definir_status(self, status):
        permitidos = {item[0] for item in self.STATUS_CHOICES}
        if status not in permitidos:
            raise ValueError('Status inválido.')
        self.status = status
        if status == self.STATUS_ENCERRADA:
            from django.utils.timezone import now
            self.encerrado_em = now()
        else:
            self.encerrado_em = None
        self.save(update_fields=['status', 'encerrado_em', 'atualizado_em'])


class MensagemAjuda(models.Model):
    ORIGEM_CLIENTE = 'cliente'
    ORIGEM_SUPORTE = 'suporte'
    ORIGEM_CHOICES = [
        (ORIGEM_CLIENTE, 'Cliente'),
        (ORIGEM_SUPORTE, 'Suporte'),
    ]

    conversa = models.ForeignKey(
        ConversaAjuda,
        on_delete=models.CASCADE,
        related_name='mensagens',
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mensagens_ajuda',
    )
    origem = models.CharField(max_length=16, choices=ORIGEM_CHOICES)
    texto = models.TextField(max_length=4000)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['criado_em', 'id']
        verbose_name = 'Mensagem de ajuda'
        verbose_name_plural = 'Mensagens de ajuda'

    def __str__(self):
        return f'{self.origem} #{self.pk}'
