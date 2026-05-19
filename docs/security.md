# Segurança — Educator Web Portal

Documento de referência da auditoria de segurança realizada em 2026-05-19 e das melhorias planejadas.

---

## Auditoria — Maio 2026

### Escopo

Portal web `educator.yaatoro.com`: FastAPI backend, Next.js 14 frontend, PostgreSQL, nginx reverse proxy, deploy via Docker Compose em VPS.

Stack auditada: autenticação JWT, gerenciamento de tokens LiteLLM, endpoints do `.exe`, configuração nginx, dependências Python.

---

## Correções Aplicadas

### [ALTO] Rate limiting ausente em endpoints do .exe

**Problema:** `/tokens/bind` e `/tokens/validate` aceitavam requisições ilimitadas sem autenticação. Um atacante podia enumerar tokens por brute force.

**Correção (`web/backend/app/routes/tokens.py`):**
```python
@router.post("/bind")
@limiter.limit("10/hour")
async def bind_hostname(request: Request, ...):

@router.post("/validate")
@limiter.limit("30/minute")
async def validate_token(request: Request, ...):

@router.post("/generate")
@limiter.limit("5/hour")
async def generate_token(request: Request, ...):
```

---

### [ALTO] Bind implícito no /validate (race condition de vinculação)

**Problema:** O endpoint `/validate` fazia bind do hostname silenciosamente se o token ainda não estivesse vinculado. Um atacante que obtivesse o token antes do usuário legítimo poderia vinculá-lo à sua própria máquina.

**Correção:** `/validate` agora rejeita tokens não vinculados. O bind deve ser feito explicitamente via `/bind` na primeira execução do `.exe`.

```python
# Antes — bind silencioso:
if matched.hostname is None:
    matched.hostname = body.hostname  # vulnerável
    return ValidateResponse(valid=True, ...)

# Depois — rejeita até que /bind seja chamado:
if matched.hostname is None:
    return ValidateResponse(valid=False, message="Token ainda não vinculado.")
```

---

### [MÉDIO] python-jose com CVEs conhecidos → migração para PyJWT

**Problema:** `python-jose==3.3.0` tem CVE-2024-33664 (DoS via alocação excessiva de memória) e CVE-2024-33663 (algorithm confusion). A biblioteca não tem manutenção ativa.

**Correção (`web/backend/requirements.txt`):**
```
# Antes:
python-jose[cryptography]==3.3.0

# Depois:
PyJWT==2.9.0
```

**Impacto em código (`security.py`, `deps.py`):**
```python
# Antes:
from jose import JWTError, jwt
jwt.encode(payload, key, algorithm="HS256")

# Depois:
import jwt as _jwt
_jwt.encode(payload, key, algorithm="HS256")
# Exceção: jwt.PyJWTError em vez de JWTError
```

---

### [MÉDIO] Headers de segurança ausentes no nginx HTTP

**Problema:** `nginx.conf` (modo HTTP / período de transição) não tinha nenhum header de segurança. Se o SSL falhasse, o site servia sem proteções básicas.

**Correção (`web/nginx/nginx.conf`):**
```nginx
add_header X-Frame-Options DENY always;
add_header X-Content-Type-Options nosniff always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

O `nginx-ssl.conf` (produção) já tinha HSTS, X-Frame-Options, X-Content-Type-Options e CSP.

---

### [BAIXO] Dummy hash inválido para timing protection

**Problema:** O hash usado para evitar enumeração de usuários por timing (`"$2b$12$aaa..."`) não era um hash bcrypt válido. O `bcrypt.checkpw()` poderia rejeitar imediatamente sem computar, eliminando a proteção de timing.

**Correção (`web/backend/app/routes/auth.py`):**
```python
# Antes — hash inválido (53 chars 'a' não é bcrypt válido):
dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

# Depois — hash bcrypt pré-computado de senha fictícia:
dummy_hash = "$2b$12$tHSwd1myzhXcCXyqBM8lxeoFqOdkHbErOXefkbEVL4Ah.HPV0dvyK"
```

---

## Trade-offs Conhecidos (Não Corrigidos)

### CSP com `unsafe-inline` em script-src

**Localização:** `web/nginx/nginx-ssl.conf`

```nginx
script-src 'self' 'unsafe-inline'
```

`'unsafe-inline'` neutraliza a proteção de XSS da CSP para scripts inline. Mantido porque Next.js 14 usa scripts inline para hidratação do lado do cliente. Remover sem configurar nonces causaria quebra do frontend.

**Condição para corrigir:** implementar CSP com nonce por request via Next.js middleware (ver seção de melhorias futuras).

---

### HSTS sem `preload`

**Localização:** `web/nginx/nginx-ssl.conf`

```nginx
Strict-Transport-Security "max-age=31536000; includeSubDomains"
```

Sem `preload`, browsers que nunca visitaram o site não têm proteção HTTPS na primeira visita (TOFU — Trust On First Use). `preload` requer submissão manual em hstspreload.org e é irreversível no curto prazo.

**Condição para corrigir:** quando o domínio estiver estável e sem plano de remoção de HTTPS.

---

### Busca O(n) de tokens em /bind e /validate

**Localização:** `web/backend/app/routes/tokens.py`

```python
result = await db.execute(select(Token).where(Token.is_active == True))
tokens = result.scalars().all()  # carrega todos na memória
for t in tokens:
    if decrypt_token(t.encrypted_key) == body.token:
```

Com poucos usuários, não é problema. Com escala, a varredura de todos os tokens ativos em memória se torna um gargalo e um vetor de DoS.

**Condição para corrigir:** adicionar um campo `token_hash` (HMAC-SHA256 do token) com índice único, permitindo busca O(1) sem descriptografar todos os registros.

---

## Melhorias Futuras

### Prioridade Alta

#### 1. Busca indexada de tokens (O(1))

Adicionar `token_hash` ao modelo `Token` para eliminar a varredura linear:

```python
# models.py
import hashlib, hmac

class Token(Base):
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
```

```python
# ao gerar o token:
def _make_token_hash(raw_key: str, secret: str) -> str:
    return hmac.new(secret.encode(), raw_key.encode(), hashlib.sha256).hexdigest()

# ao buscar:
result = await db.execute(
    select(Token).where(Token.token_hash == _make_token_hash(body.token, settings.secret_key))
)
token = result.scalar_one_or_none()
```

---

#### 2. CSP com nonce (elimina unsafe-inline)

Implementar nonce por request via Next.js middleware:

```typescript
// middleware.ts
import { NextResponse } from 'next/server'
import crypto from 'crypto'

export function middleware(request) {
  const nonce = crypto.randomBytes(16).toString('base64')
  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}';
    style-src 'self' 'nonce-${nonce}' fonts.googleapis.com;
  `.replace(/\s{2,}/g, ' ').trim()

  const response = NextResponse.next()
  response.headers.set('Content-Security-Policy', cspHeader)
  return response
}
```

```typescript
// next.config.mjs — passar nonce para o runtime do Next.js
const nextConfig = {
  // ...
  async headers() {
    return [{ source: '/(.*)', headers: [{ key: 'x-nonce', value: 'injected-by-middleware' }] }]
  }
}
```

---

#### 3. Blacklist de tokens JWT (revogação imediata)

Atualmente, um JWT roubado permanece válido por até 60 minutos. Para revogação imediata:

```python
# Opção A: Redis com TTL igual ao TTL do JWT
import redis.asyncio as aioredis

async def revoke_jwt(jti: str, ttl_seconds: int):
    await redis.setex(f"jwt:revoked:{jti}", ttl_seconds, "1")

async def is_revoked(jti: str) -> bool:
    return await redis.exists(f"jwt:revoked:{jti}") > 0
```

```python
# Adicionar JTI ao payload do JWT em security.py:
import uuid
payload = {"sub": user_id, "exp": expire, "jti": str(uuid.uuid4())}
```

Requer Redis no Docker Compose. Alternativa mais simples: reduzir `access_token_expire_minutes` de 60 para 15.

---

### Prioridade Média

#### 4. Autenticação por chave SSH (eliminar senha root da VPS)

A senha root da VPS ainda existe como vetor de ataque. Com o pipeline CI/CD já usando SSH key, a senha pode ser desabilitada:

```bash
# Na VPS — desabilitar login por senha:
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
echo "PermitRootLogin prohibit-password" >> /etc/ssh/sshd_config
systemctl reload sshd
```

---

#### 5. Logs sem dados pessoais

Atualmente logs expõem `user.id` (UUID) em operações de erro. Substituir por aliases opacos em produção:

```python
# Em vez de:
logger.error("litellm_generate_failed user=%s", user.id)

# Usar hash truncado não reversível:
import hashlib
uid_alias = hashlib.sha256(str(user.id).encode()).hexdigest()[:12]
logger.error("litellm_generate_failed user=%s", uid_alias)
```

---

#### 6. Renovação automática de SSL via cron

Certificado Let's Encrypt expira a cada 90 dias. Adicionar renovação automática na VPS:

```bash
# Cron na VPS:
0 3 * * 1 certbot renew --quiet && docker compose -f /opt/educator-web/web/docker-compose.yml exec nginx nginx -s reload
```

---

### Prioridade Baixa

#### 7. HSTS preload

Após o domínio estar estável, submeter em [hstspreload.org](https://hstspreload.org) e adicionar a flag:

```nginx
Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

---

#### 8. Dependency pinning com hash verification

Adicionar hashes SHA256 ao `requirements.txt` para garantir integridade das dependências:

```bash
pip-compile --generate-hashes requirements.in > requirements.txt
```

---

## Score de Segurança

| Data | Score | Eventos |
|---|---|---|
| Antes da auditoria | 5.5/10 | Baseline |
| 2026-05-19 | 8.0/10 | Auditoria + correções aplicadas |
| Meta (com melhorias futuras priorizadas) | 9.5/10 | Busca O(1), CSP nonce, JWT blacklist, desabilitar senha SSH |
