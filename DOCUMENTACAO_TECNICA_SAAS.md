# Documentação técnica — estado atual do SaaS

**Projeto:** `portal_noticias`  
**Data desta documentação:** 16 de setembro de 2026  
**Branch analisada:** `master` (alinhada com `origin/master`)  
**Escopo:** somente o que existe no código, nas migrations, em `.env.example`, `requirements.txt`, `procfile` e no histórico Git visível.  
**Convenção:** o que não pôde ser lido no repositório está marcado como *Não identificado no código atual.*

---

## 1. Visão geral do projeto

SaaS Django de **portais de notícias multi-tenant**. Uma única aplicação atende:

- a **plataforma comercial** (landing, `/comece/`, webhook Kiwify, painel `/master/`);
- o **site público de cada cliente** (jornal local);
- o **painel do cliente** em `/app/`.

Apps Django instalados (`INSTALLED_APPS`): `django.contrib.*` (admin, auth, contenttypes, sessions, messages, staticfiles, sitemaps), `plataforma`, `noticias`.

Dependências declaradas em `requirements.txt` (versões pinadas): Django `5.2.4`, gunicorn, WhiteNoise, dj-database-url, Pillow, psycopg / psycopg2 / psycopg2-binary, asgiref, packaging, sqlparse, typing_extensions, tzdata.

Na execução local dos testes desta documentação, o interpretador usou **Django 5.1.6** (`python -c "import django"`). O arquivo `requirements.txt` declara **5.2.4**. Qual versão está no Render **não está no repositório**.

Idioma e fuso: `LANGUAGE_CODE = 'pt-br'`, `TIME_ZONE = 'America/Porto_Velho'`, `USE_TZ = True`.

---

## 2. Arquitetura geral

Arquitetura **monólito Django** (WSGI), um banco, **isolamento lógico por `portal_id`**.

Fluxo HTTP:

1. `SecurityMiddleware` → WhiteNoise → Session → Common → CSRF → Auth.
2. `plataforma.middleware.TenantMiddleware` resolve o tenant pelo Host, grava `request.portal` / `request.membership` e o contexto (`contextvars`) usado pelos managers.
3. `SecurityHeadersMiddleware` acrescenta cabeçalhos.
4. Views em `noticias` (público) ou `plataforma` (`/app/`, `/master/`, vendas, webhook).

Não há fila de jobs, Celery, Redis, microserviços ou API REST genérica identificados no código. Há proxy HTTP síncrono para Open-Meteo (`/api/clima/`) e POST HTTPS para a API da Resend.

Ponto de entrada: `manage.py`, `portal_noticias.wsgi:application` (`procfile`: `web: gunicorn portal_noticias.wsgi:application`). Existe `portal_noticias/asgi.py`; o Procfile **não** o usa.

---

## 3. Estrutura das aplicações Django

| App | Papel confirmado |
|-----|------------------|
| `portal_noticias` | Projeto: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py` |
| `plataforma` | Tenant, Cliente, Assinatura, Plano, Membership, webhooks, e-mail, Master, `/app/`, vendas `/comece/` |
| `noticias` | Conteúdo público, auth de usuário, PWA, SEO, engajamento, contribuição, admin de conteúdo |

Comando de gestão: `noticias.management.commands.criar_admin` (superuser a partir de variáveis de ambiente).

---

## 4. Modelo multi-tenant

- Um registro `plataforma.Portal` = um tenant.
- Conteúdo (`Categoria`, `Noticia`, `Contribuicao`, `Anuncio`) tem `ForeignKey` para `Portal` e usa `TenantManager` (`objects`) + `all_objects` (sem filtro).
- Resolução **pelo Host**, não por `?portal_id=` nas URLs públicas/painel.
- Fallback legado (`Portal.get_default()`, slug `noticiasjiparana`) só se `TENANT_COMPAT_FALLBACK` estiver ligado **e** o Host for de plataforma/local. Em `PRODUCTION=true` o default do setting é `false`.
- Seeds de migration: portal legado `noticiasjiparana` e portal de teste `portalbeta`.

`django.contrib.auth.User` é **global** (não há `AUTH_USER_MODEL` customizado). Vínculo operacional ao tenant: `Membership`. Perfil público (`noticias.Perfil`) é 1:1 com User, sem `portal_id`.

---

## 5. Como o Portal é identificado pelo Host/domínio

Implementação: `plataforma.resolvers`.

1. Host sem porta, minúsculo.
2. Se `Portal.custom_domain` (iexact) bater com o Host → esse portal.
3. Se o Host for “plataforma/local” → **nenhum** tenant (`None`): `PLATFORM_HOSTS`, `localhost`, `127.0.0.1`, `testserver`, ou primeiro label em `www`, `admin`, `plataforma`, `localhost`, `testserver`, `127`.
4. Caso contrário, o primeiro label do Host é o **slug** (`{slug}.{TENANT_BASE_DOMAIN}`).

`TENANT_BASE_DOMAIN` default: `portalnoticias.com.br`.  
Hosts de plataforma hardcoded em settings: `portalnoticias.com.br`, `www.portalnoticias.com.br`, `meu-site-noticias.onrender.com`, mais `localhost` / `127.0.0.1` / `testserver`. Env `PLATFORM_HOSTS` pode acrescentar.

`/` no host de plataforma renderiza landing SaaS (`plataforma/home.html`). `/` no host de tenant renderiza o jornal (`NoticiaListView`).

---

## 6. Isolamento por `portal_id`

- `TenantManager`: em request com portal, `filter(portal_id=portal.pk)`; se request sem portal, queryset vazio; fora de HTTP (shell/migrations) não filtra.
- `assign_portal` / `assign_default_portal`: preenche `portal` pelo contexto; em HTTP sem portal levanta `ValueError`.
- Views `/app/` usam `Noticia.objects` (já filtrado) e `get_object_or_404` no queryset do tenant.
- Django admin de conteúdo: `TenantAdminMixin` (superuser vê todos; demais só o portal do Host).
- Models de plataforma (`Portal`, `Cliente`, `Assinatura`, etc.) **não** usam `TenantManager`.
- `Comentario` e `Curtida` isolam-se via FK `noticia` (que tem `portal_id`).
- Cache de anúncios e nav usam chaves `tenant:{pk}:...` (`noticias.utils.cache_key_portal`). **Atenção:** em `noticias/views.py` a classe `NoticiasBaseMixin` está **definida duas vezes**; a segunda (efetiva) usa chaves globais `categorias_sidebar`, `noticias_populares`, `noticias_destaques_v2` **sem** prefixo de tenant.

---

## 7. Modelos principais e relacionamento

```
Plano 1───N Portal
Cliente 1───N Portal (FK anulável)
Cliente 1───N Assinatura
Portal 1───1 Assinatura (OneToOne)
Plano 1───N Assinatura
User  N───N Portal via Membership (unique usuario+portal)
Portal 1───N Categoria | Noticia | Contribuicao | Anuncio | Membership | EmailLog | AuditLog
Noticia 1───N NoticiaImagem | Comentario | Curtida
Contribuicao 1───N ContribuicaoImagem
User 1───1 Perfil
WebhookEvent (eventos externos; não FK obrigatória a Portal)
```

---

## 8. Cliente

Model `plataforma.Cliente`: `nome`, `email` (unique), `telefone`, `status` (`ativo` / `inativo`), `criado_em`.

Criado/atualizado no onboarding Kiwify (`get_or_create` por e-mail). Listagem/detalhe/reenvio de acesso no Master. Admin Django restrito a superuser (`SuperuserOnlyAdminMixin`).

---

## 9. Assinatura

Model `plataforma.Assinatura`: FK Cliente (`PROTECT`), OneToOne Portal (`PROTECT`), FK Plano (`PROTECT`), `status`, IDs Kiwify (`kiwify_subscription_id`, `kiwify_order_id`, `kiwify_transaction_id`), datas (`iniciado_em`, `proximo_vencimento`, `cancelado_em`, `bloqueado_em`).

Status: `aguardando_pagamento`, `ativa`, `pagamento_pendente`, `atrasada`, `cancelada`, `bloqueada`.

Constraints unique (quando não vazio): `kiwify_order_id`, `kiwify_subscription_id`.

Sincroniza `Portal.pagamento_status` e `Portal.plano` / `cliente`. Cancelamento/atraso **não apaga** conteúdo; bloqueio define `Portal.status = bloqueado`.

Painel do cliente: `/app/assinatura/` (papel admin do portal). Master: `/master/assinaturas/`.

---

## 10. Membership e permissões

`Membership`: `usuario`, `portal`, `papel`, `ativo`, unique `(usuario, portal)`.

Papéis: `admin`, `editor`, `autor`, `moderador`.

| Recurso | Papéis (`plataforma.permissions`) |
|---------|-----------------------------------|
| Notícia | admin, editor, autor |
| Categoria | admin, editor |
| Anúncio | admin |
| Moderação (contribuição/comentário/curtida no mapping) | admin, moderador |
| Usuários da equipe, aparência, SEO, config, assinatura | admin (views `/app/`) |

Autor no `/app/noticias/` vê só `criado_por=request.user` (exceto superuser).  
`is_platform_master` = usuário autenticado **e** `is_superuser`. Master ignora papel e vê todos os tenants no admin.

---

## 11. Usuários e autenticação

- Modelo: `django.contrib.auth.models.User`.
- Login: `/entrar/` (`EntrarView` + `LoginForm`).
- Cadastro público: `/cadastro/` e `/criar-conta/` (`CadastroForm` cria User + `Perfil`).
- Logout: `/sair/` (GET ou POST).
- Conta: `/conta/`.
- Recuperação: `/senha/esqueci/` … `/senha/redefinir/<uidb64>/<token>/` (`RecuperarSenhaForm` envia via Resend / `EmailLog.TIPO_RECUPERACAO`).
- Alteração autenticada: `/senha/alterar/`.
- `LOGIN_URL = '/entrar/'`, timeout de reset default 3600 s, sessão DB, cookie 14 dias (override `SESSION_COOKIE_AGE`).
- Superuser: comando `criar_admin` com `DJANGO_SUPERUSER_*`; não altera usuário existente.
- Signal: User criado → `Perfil.get_or_create`.
- Destino pós-login (`destino_pos_login`): master se superuser; um portal → `/app/` no host do tenant; vários → `/selecionar-portal/`; só portais inativos → `/acesso-indisponivel/`; sem membership → `/comece/`.
- Em localhost, `/app/` usa sessão `app_portal_id` ou o único Membership ativo — **não** `Portal.get_default()`.

---

## 12. Área pública do portal

Rotas em `noticias/urls.py` (incluídas em `''`):

- `/` jornal (se Host = tenant)
- `/videos/`, `/experiencia/`, `/api/clima/`
- `/exclusivo/`, `/exclusivo/noticia/<id>/`
- `/noticia/<id>/`, curtir/comentar
- `/categoria/<slug>/`, `/contribuir/`
- auth (entrar, cadastro, senha, conta, parceria)
- `/selecionar-portal/`, `/acesso-indisponivel/`
- `/painel/` (alias de envios; mesma view do app)
- PWA: `manifest.webmanifest`, `sw.js`, `/pwa/icon/<size>.png`
- `sitemap.xml`, `robots.txt` (raiz do projeto)

Identidade visual/SEO: `noticias.context_processors.site_context` + `plataforma.identity`. AdSense no HTML só se `portal.adsense_client_id` preenchido.

Portal `status != ativo`: público e `/app/` recebem 403 (`portal_indisponivel.html` ou `403.html`), exceto `/webhooks/` e `/comece` e superuser.

---

## 13. Área `/app/`

Prefixo `path('app/', include('plataforma.urls'))`. Mixin `AppAccessMixin`: login + portal no request + `has_portal_role`.

Rotas: dashboard; notícias CRUD; categorias CRUD; fotos, vídeos, galeria; envios aprovar/rejeitar; autores; usuários (admin cria membro com senha no formulário); publicidade; assinatura; SEO; aparência; configurações.

`/painel/` e `/painel/aprovar|rejeitar/` apontam para as mesmas views de envios.

---

## 14. Área `/master/`

Somente `is_superuser` (`MasterRequiredMixin`). Demais autenticados: 403.

Rotas: dashboard, busca, saúde, configurações + e-mail teste, webhooks (detalhe + reprocessar), auditoria, clientes (detalhe + reenviar acesso), portais (detalhe + ação ativar/bloquear/plano), assinaturas, planos (editar checkout Kiwify, IDs, preços).

---

## 15. Onboarding `/comece/`

- `/comece/` — comparação de planos (`Plano.ativo` e `preco_mensal != 0`).
- `/comece/<codigo>/` — checkout do plano (`codigo` = slug do Plano). Se `checkout_url` existir, link externo Kiwify; senão, mensagem de “em configuração”. **Nenhum** Cliente/Portal é criado nesta tela.

`/` em host de plataforma = landing `home.html`, não a lista de planos.

---

## 16. Integração com Kiwify

Checkout: URL por plano (`Plano.checkout_url`, `kiwify_product_id`, `kiwify_plan_id`), cadastrados no Master.

Webhook de produto/assinatura do painel (não a API bancária Ed25519), documentado em `plataforma/services/kiwify.py`.

Segredo: `KIWIFY_WEBHOOK_SECRET`. Sem segredo, `webhook_autentico` retorna `False`.

Assinatura aceita (query `?signature=` ou campo `signature` no payload): HMAC-SHA1(token, order_id); SHA1(order_id+token); HMAC-SHA1(token, corpo bruto). MD5 legado é rejeitado (teste dedicado).

---

## 17. Webhook da Kiwify

- URL: `POST /webhooks/kiwify/` (`csrf_exempt`).
- JSON ou POST form; 400 se JSON inválido; 401 se assinatura inválida; 400 sem `order_id`.
- Persistência `WebhookEvent` (`provedor='kiwify'`, unique `provedor+tipo+id_externo` com `id_externo=order_id`). Evento já `processado` → `{duplicado: true}`.
- Classificação: aprovado (`compra_aprovada`, `order_approved`, `subscription_renewed`); pendente (pix/boleto/recusa); atrasada (`subscription_late`); cancelada (cancelamento, reembolso, chargeback); resto ignorado 200.
- Master pode reprocessar. `tentativas` incrementa. Erros não marcam `processado=True`.

---

## 18. Criação automática de cliente/portal/usuário

`provisionar_pagamento_aprovado` (evento aprovado):

1. Exige `Customer.email`.
2. Se já houver Assinatura pelo subscription_id/order_id → reativa, não duplica.
3. Senão: Cliente; Plano (plan_id → product_id → primeiro plano pago ativo → `basico` → primeiro Plano); Portal (slug via `gerar_slug_portal`, status ativo, pagamento pago); `Categoria` slug `geral`; User (reusa e-mail ou cria com senha aleatória de 12 chars); Membership admin; Assinatura ativa; audit `onboarding_aprovado`; e-mail de acesso **após commit**.

Cancelamento: Assinatura bloqueada + Portal bloqueado, dados preservados.

---

## 19. Integração com Resend

`plataforma.services.email`: POST `https://api.resend.com/emails`, Bearer `RESEND_API_KEY`, timeout 15 s. “Pronto para envio” = chave presente (`smtp_pronto_para_envio`). Sem chave: `EmailLog.STATUS_NAO_CONFIGURADO`.

Settings ainda leem `EMAIL_BACKEND`, `EMAIL_HOST`, etc.; o envio da plataforma **não** usa SMTP Django — só Resend. Diagnóstico Master/saúde chama isso de “SMTP” no texto da UI.

`ADSENSE_PLATFORM_CLIENT_ID` existe em settings/`.env.example` e **não é lido** em views/templates (só `Portal.adsense_client_id`).

---

## 20. Fluxo de envio do e-mail de acesso

`enviar_acesso`: link de redefinição Django (`default_token_generator` + `uidb64`), URLs `https://{host}/` e `https://{host}/app/` (`custom_domain` tem prioridade sobre `{slug}.{TENANT_BASE_DOMAIN}`). Se `SITE_URL` estiver definido, a **base do link de senha** usa `SITE_URL` (não o host do tenant).

Corpo texto: site, painel, username, link (~1 h). **Não envia a senha permanente.** Tipo `onboarding` ou `reenvio_acesso` (Master). Logs em `EmailLog` (segredos sanitizados).

---

## 21. PWA

Por tenant, no Host do portal. Templates públicos: `rel=manifest` e `navigator.serviceWorker.register` somente se `pwa_disponivel` (`resolve_portal_from_host` ≠ None). Host de plataforma: 404 no manifest/SW/ícone; HTML da landing **não** registra SW.

---

## 22. Manifest

`GET /manifest.webmanifest` → JSON (`application/manifest+json`, `Cache-Control: no-cache`). Campos: `id`, `name` (máx. 45), `short_name` (cidade ou nome, 12 chars), `description`, `start_url` `/`, `scope` `/`, `display` standalone, `orientation` portrait-primary, `lang` pt-BR, cores do portal, ícones 192/512 (`any` e `maskable`).

---

## 23. Service Worker

`GET /sw.js`: JS inline — `install` skipWaiting, `activate` clients.claim, `fetch` **sempre network** (`fetch(event.request)`), sem cache de páginas. Cabeçalho `Service-Worker-Allowed: /`.

---

## 24. Ícones

`GET /pwa/icon/192.png` e `/pwa/icon/512.png` (outros sizes 404). PNG gerado (Pillow): fundo `cor_primaria`; tenta logo, favicon ou OG; senão inicial do nome. `Cache-Control: public, max-age=300`. Não há arquivos estáticos de ícone PWA em `static/`.

---

## 25. Regras de disponibilidade do PWA por tenant

Disponível **somente** se o Host resolver um `Portal` (slug ou `custom_domain`). Independente de `status` ativo no resolver do PWA (o middleware ainda pode 403 o HTML se o portal estiver inativo). Plataforma/localhost: indisponível.

---

## 26. Domínios e subdomínios

Confirmado no código:

- Apex/www/`meu-site-noticias.onrender.com` = plataforma.
- `{slug}.TENANT_BASE_DOMAIN` = tenant.
- `custom_domain` no model + resolução iexact; geração de URL HTTPS canônica.
- `ALLOWED_HOSTS` de produção default inclui `.portalnoticias.com.br` (subdomínios).
- `CSRF_TRUSTED_ORIGINS` de produção: HTTPS apex, www, `https://*.portalnoticias.com.br`, host Render.

DNS, certificados wildcard, apontamento no registrador: **Não identificado no código atual** (configuração externa).

Slugs reservados (`plataforma.slugs.SLUGS_RESERVADOS`): labels de plataforma + `app`, `master`, `api`, `webhooks`, `comece`, `static`, `media`, etc.

---

## 27. Render

Confirmado no repositório:

- `procfile`: gunicorn WSGI.
- Host `meu-site-noticias.onrender.com` em `PLATFORM_HOSTS_PRODUCAO` / `ALLOWED_HOSTS_PRODUCAO`.
- `dj-database-url` + `DATABASE_URL`; `DATABASE_SSL` default true.
- WhiteNoise para estáticos; `STATIC_ROOT = staticfiles/`.
- Commits históricos citam PostgreSQL e deploy Render.

**Não identificado no código atual:** `render.yaml`, Dockerfile, painel Render (plano, disco, variáveis reais, health check). Há `asgi.py` não usado pelo Procfile.

---

## 28. Variáveis de ambiente

Fonte: `settings.py` + `.env.example`. Arquivo `.env` é carregado se existir (`setdefault`; não sobrescreve o SO). `.gitignore` ignora `.env`.

| Variável | Uso no código |
|----------|----------------|
| `DEBUG`, `PRODUCTION`, `SECRET_KEY` | modo, HTTPS/HSTS, chave |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | hosts |
| `DATABASE_URL`, `DATABASE_SSL` | Postgres vs SQLite `db.sqlite3` |
| `SITE_URL`, `TENANT_BASE_DOMAIN`, `PLATFORM_HOSTS`, `TENANT_COMPAT_FALLBACK` | URLs/tenant |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `RESEND_API_KEY`, `NOTIFY_EMAILS` | e-mail (envio efetivo = Resend) |
| `PASSWORD_RESET_TIMEOUT`, `SESSION_COOKIE_AGE`, `SERVE_MEDIA` | auth/mídia |
| `SECURE_HSTS_SECONDS`, `SECURE_HSTS_PRELOAD` | produção |
| `LOGIN_THROTTLE_*`, `SENSITIVE_THROTTLE_*` | rate limit |
| `DEFAULT_FILE_STORAGE`, `AWS_*` | lidos; **não** ligados a `STORAGES` |
| `KIWIFY_WEBHOOK_SECRET`, `ADSENSE_PLATFORM_CLIENT_ID` | webhook; AdSense plataforma não usado |
| `DJANGO_SUPERUSER_*` | comando `criar_admin` |
| `FILE_UPLOAD_MAX_MEMORY_SIZE`, `DATA_UPLOAD_MAX_MEMORY_SIZE` | default ~50 MB |

Valores reais de produção: **Não identificado no código atual.**

---

## 29. Banco de dados

- Sem `DATABASE_URL`: SQLite em `BASE_DIR/db.sqlite3` (arquivo gitignored).
- Com `DATABASE_URL`: `dj_database_url.config`, `conn_max_age=600`, SSL conforme `DATABASE_SSL`.
- PK default `BigAutoField`.
- Migrations: `plataforma` `0001`–`0006`; `noticias` `0001`–`0016`.

Engine no Render: **Não identificado no código atual** (só o padrão `DATABASE_URL`).

---

## 30. Segurança

Confirmado: CSRF Django; cookies HttpOnly + SameSite Lax; em `PRODUCTION` SSL redirect, cookies Secure, HSTS, `SECURE_PROXY_SSL_HEADER`; `X_FRAME_OPTIONS=DENY`; nosniff; referrer same-origin; COOP; CSP `frame-ancestors 'self'` em HTML; Permissions-Policy; senha min. 8 + validadores Django; `safe_redirect` só same-host; `next` pós-login não libera `/master` ou `/app` sem permissão; admin de plataforma só superuser; webhook autentica assinatura; logs mascaram senhas/tokens; uploads com extensão/MIME/tamanho (`noticias.image_utils`); `SECRET_KEY` obrigatória se não DEBUG ou se PRODUCTION; audit em login/logout/falha.

`CACHES` **não** está em `settings.py` (default Django locmem). Throttle usa esse cache.

---

## 31. Rate limiting

`plataforma.security.throttle_blocked`: contador por IP + `scope` no cache.

- Login POST: `LOGIN_THROTTLE_LIMIT` default 8 / `WINDOW` 300 s.
- Cadastro, reset de senha, contribuir POST: `SENSITIVE_THROTTLE_LIMIT` 20 / 600 s.

IP: em produção, primeiro de `X-Forwarded-For`; senão `REMOTE_ADDR`. Resposta 429 texto. Sem persistência além do cache.

---

## 32. Proteções contra isolamento entre tenants

Confirmado em código e testes (`tests_isolamento`, `tests_seguranca`, `tests_comercial`, `tests_identidade`, `tests_pwa`, `tests_urls_portal`, `tests_pos_login`): listagens/IDOR 404; categoria/anúncio por portal; painel de um host não age no outro; sitemap/robots por request; identidade/PWA sem cruzar marcas; webhook/provisionamento não duplica; cliente A não acessa B no `/app/`; `next` externo bloqueado.

Pontos reais no código atual (não corrigidos aqui): `NoticiasBaseMixin` duplicado com cache global na versão efetiva; `Perfil.is_assinante` global; limites de plano não enforced nas views; `SITE_URL` pode unificar links de senha.

---

## 33. Redirecionamentos e URLs

| Caminho | Destino |
|---------|---------|
| `/` plataforma | landing SaaS |
| `/` tenant | jornal |
| Login | `destino_pos_login` |
| Cadastro | idem |
| Sem membership | `/comece/` |
| Vários portais | `/selecionar-portal/` |
| Portal inativo (membro) | `/acesso-indisponivel/` |
| `/app/` sem permissão | seleção / único portal / vendas / 403 |
| Master sem superuser | 403 |
| Logout | `index` |
| Open redirect | recusado (`safe_redirect` / `url_has_allowed_host_and_scheme`) |

Handlers 400/403/404/500 em `plataforma.views_errors`.

---

## 34. Uploads e mídia

- `MEDIA_URL=/media/`, `MEDIA_ROOT=BASE_DIR/media` (gitignored).
- Servir via Django só se `DEBUG` ou `SERVE_MEDIA`.
- Paths `portais/{slug}/...` (logo/favicon/og; notícias; galeria; envios; vídeos; anúncios) com UUID.
- Imagens: jpg/png/webp/gif, máx. 8 MB, lado 1600, JPEG q82; vídeos mp4/webm 50 MB; galeria máx. 20 fotos; SVG/PHP/exe/js etc. recusados.
- Limites Django upload ~50 MB.
- `DEFAULT_STORAGE` / AWS no env **não** configuram `STORAGES`. Produção de mídia no Render: **Não identificado no código atual.**

---

## 35. Testes automatizados

`python manage.py test`. Arquivos:

- `noticias/tests.py`
- `plataforma/tests.py`
- `tests_identidade.py`, `tests_isolamento.py`, `tests_seguranca.py`, `tests_ui.py`
- `tests_pos_login.py`, `tests_comercial.py`, `tests_operacao.py`
- `tests_pwa.py`, `tests_urls_portal.py`

Cobrem tenant, IDOR, Kiwify, Resend (mocks), Master, PWA, URLs, auth, uploads.

---

## 36. Quantidade atual de testes e resultado

Execução em 16/09/2026, workspace `C:\sites\portal_noticias`, `python manage.py test --verbosity=1`:

- **Found 152 test(s).**
- **Ran 152 tests in 29.243s**
- **OK** (exit code 0)
- System check: 0 issues

Durante a suíte o logger registrou tentativas Resend (HTTP 422 / 403 / não configurado) em testes de e-mail; a suíte mesmo assim fechou **OK**. Warning: paginação de `Portal` unordered em um teste.

---

## 37. Estrutura de arquivos importantes

```
portal_noticias/
  manage.py
  procfile
  requirements.txt
  .env.example
  .gitignore
  portal_noticias/settings.py urls.py wsgi.py asgi.py
  plataforma/          models, middleware, resolvers, permissions, views_*, services/, templates/, migrations/
  noticias/            models, views*, urls, templates, image_utils, management/commands, migrations/
  static/              css (ds, portal, public, app, experiencia), js (app, portal-nav, engagement, experiencia)
  templates/           (DIRS do settings; apps também usam APP_DIRS)
```

Não há README no repositório. Não há `render.yaml`.

---

## 38. Git e branches relevantes

Confirmado em 16/09/2026:

- Branch atual: `master`, *up to date* with `origin/master`.
- Locais: `master`, `etapa-6-5-ui`, `saas-v1`.
- Remotos: `origin/master`, `origin/etapa-6-5-ui`, `origin/HEAD → origin/master`.
- Working tree **limpo** antes deste arquivo de documentação.

Remote URL: **Não identificado nesta sessão** (não foi executado `git remote -v` com saída gravada).

---

## 39. Commits relevantes encontrados no histórico

`git log --oneline` (mais recentes primeiro), mensagens literais:

| Hash | Mensagem |
|------|----------|
| `6e3f1aa` | feat: adiciona suporte PWA multi-tenant |
| `d3fe171` | Adiciona aliases dos eventos Kiwify |
| `f9d75ce` | Corrige assinatura HMAC-SHA1 do webhook Kiwify |
| `9e23c9f` | fix: aceitar assinatura Kiwify via query string |
| `66c9aa0` | Exibir erro detalhado do Resend no Master |
| `5fb353c` | Migrar envio de email para Resend API |
| `ef34a78` | Adicionar URLs próprias dos portais SaaS |
| `dac111d` | Implementar etapa 7.1 de operacao e e-mails |
| `74c50d7` | Preparar projeto SaaS para producao no Render |
| `58ea48e` | Adicionar contratação por plano em /comece/. |
| `138185a` | refinar UI UX da plataforma SaaS - etapa 6.5 |
| `ce3ed54` | Adicionar a plataforma SaaS multi-tenant e o início do refinamento de UI. |
| `b637ad2` | Parar de versionar banco SQLite e arquivos .pyc. |
| `06326d2` | Salvar o portal atual antes da evolução SaaS. |
| Commits anteriores | AdSense, PostgreSQL/Render, WhiteNoise, gunicorn, Procfile, versão inicial do portal |

---

## 40. O que já está concluído

Confirmado no código + testes OK:

- Multi-tenant por Host/slug/`custom_domain`
- Conteúdo, identidade, SEO, AdSense por portal
- `/app/` com papéis; `/master/` superuser
- Comercial `/comece/` + webhook Kiwify + provisionamento
- Resend, EmailLog, reenvio Master, saúde operacional
- PWA por tenant
- Auth, throttle, headers, IDOR coberto por testes
- Deploy WSGI/gunicorn/WhiteNoise/DATABASE_URL no repositório
- 152 testes passando nesta execução

---

## 41. O que ainda falta para produção

Itens **dependentes de configuração externa** (não dá para afirmar no Git se já foram feitos no Render/Kiwify/Resend/DNS):

- `PRODUCTION=true`, `SECRET_KEY` forte, `DEBUG=false`
- `DATABASE_URL` Postgres, `ALLOWED_HOSTS` / CSRF
- `KIWIFY_WEBHOOK_SECRET` e `checkout_url` + IDs em cada plano
- `RESEND_API_KEY` e domínio verificado no `DEFAULT_FROM_EMAIL` (teste da suíte chegou a logar 403 “domain is not verified” contra a API real em um cenário)
- DNS wildcard / custom domain / TLS
- Estratégia de mídia com `SERVE_MEDIA=false` (S3 no env **não está ligado**)
- Superuser via `criar_admin`
- URL pública do webhook no painel Kiwify

Lacunas **no código** (existem campos/env sem enforcement ou wiring): limites `max_storage_mb` / `max_usuarios` / `max_noticias_mes` não bloqueiam views; `STORAGES`/S3 não aplicados; `ADSENSE_PLATFORM_CLIENT_ID` não usado; `NoticiasBaseMixin` duplicado; versão Django requirements vs ambiente local diverge.

Estado real do serviço em produção: **Não identificado no código atual.**

---

## 42. Checklist de configuração de produção

Derivado só do que o código exige/lê:

1. `SECRET_KEY` definida; `DEBUG=false`; `PRODUCTION=true`
2. `DATABASE_URL` (+ SSL)
3. `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` (ou defaults de produção)
4. `TENANT_BASE_DOMAIN`, `PLATFORM_HOSTS`, `TENANT_COMPAT_FALLBACK` (produção default off)
5. `SITE_URL` se os links de senha devem usar um host fixo
6. `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL`
7. `KIWIFY_WEBHOOK_SECRET`; planos com `checkout_url` e IDs
8. `DJANGO_SUPERUSER_*` + `criar_admin` (ou superuser já existente)
9. Collectstatic / WhiteNoise; decisão de `SERVE_MEDIA` ou storage externo
10. Proxy HTTPS (`X-Forwarded-Proto`)
11. Webhook Kiwify → `https://<host-plataforma>/webhooks/kiwify/`
12. DNS dos subdomínios — **Não identificado no código atual** (passo operacional)

---

## 43. Checklist de criação de um novo tenant

**Automático (pagamento aprovado):** webhook autêntico → Cliente, Portal, categoria Geral, User, Membership admin, Assinatura, e-mail de acesso.

**Manual no código:** criar `Portal` (admin Django ou Master não cria portal do zero nas views Master listadas — Master ativa/bloqueia/muda plano de portal **já existente**). Criação avulsa via Django admin (superuser) é possível.

Pós-criação operacional (DNS, Kiwify produto, logo): parte **externa** / painel `/app/aparencia/`.

---

## 44. Checklist de manutenção

Confirmado como telas/comandos existentes:

- `/master/saude/`, dashboard (e-mails falhos, webhooks erro, assinaturas)
- `/master/webhooks/` + reprocessar
- `/master/configuracoes/` e-mail teste
- `/master/auditoria/`, `/master/busca/`
- Reenviar acesso no cliente
- Ativar/bloquear portal (não apaga dados)
- `criar_admin` se ainda não houver superuser
- Migrations Django (já no repo; aplicar no ambiente é operação de deploy)

Backup, monitoramento APM, rotação de chaves: **Não identificado no código atual.**

---

## 45. Possíveis pontos de atenção encontrados (sem correção)

1. `noticias/views.py`: `_qs_noticias` e `NoticiasBaseMixin` definidos **duas vezes**; vale a segunda (cache **global** e `_usuario_ve_exclusivo` via `is_staff`, não membership).
2. Limites do `Plano` não são aplicados nas views de upload/equipe/notícia.
3. `DEFAULT_FILE_STORAGE` / `AWS_*` não configuram storage Django.
4. Mídia local + `SERVE_MEDIA` default false em produção.
5. Recuperação de senha: Django `PasswordResetView` + Resend no form; `EMAIL_BACKEND` continua no settings mas o envio da plataforma é Resend.
6. `SITE_URL` pode gerar link de acesso/senha no host da plataforma em vez do tenant.
7. `Perfil.is_assinante` não é por portal.
8. Logout por GET.
9. Cadastro público cria User global sem Membership.
10. `AppUsuarioCreateView` define senha no formulário (onboarding Kiwify usa senha aleatória + link).
11. `ClimaApiView` aceita `lat`/`lon` na query (proxy Open-Meteo).
12. Placeholders Unsplash em `portal_extras` se a notícia não tem imagem.
13. AdSense `ca-pub-...` seedado na migration do portal legado (`0002_identidade_portal`).
14. `WebhookEvent.id_externo` = `order_id` (um tipo+order); renovação usa o mesmo mecanismo de unique por tipo.
15. `cancelar_ou_bloquear` com `bloquear=True` para reembolso/chargeback.
16. Cache default locmem — throttle não compartilhado entre workers.
17. Sem `SESSION_COOKIE_DOMAIN` — cookies por host.
18. Django `requirements.txt` 5.2.4 vs 5.1.6 nesta máquina de teste.
19. Testes de e-mail podem atingir a API Resend real se a chave do ambiente não for mockada em todos os casos (logs 403/422 nesta execução).
20. Warning de queryset `Portal` sem `ordering` na paginação (Master).
21. `ADSENSE_PLATFORM_CLIENT_ID` sem uso.
22. DNS/TLS/wildcard e disco persistente Render: fora do código.

---

## Como esta documentação foi produzida

Leitura de settings, URLs, models, middleware, services (Kiwify, e-mail, onboarding, acesso, webhooks), views públicas/app/master, PWA, forms, migrations, `.env.example`, `requirements.txt`, `procfile`, `.gitignore`, e `git log` / `git branch`. Suíte `manage.py test`: 152 OK. Nenhum arquivo de sistema foi modificado para esta análise; o único artefato novo pretendido é este Markdown.
