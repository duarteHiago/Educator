# Educator — Contexto Técnico e Decisões Arquiteturais

> Documento vivo. Atualizar a cada fase concluída ou decisão relevante.

---

## Visão Geral do Projeto

**Nome:** Educator  
**Tipo:** Plataforma privada de automação acadêmica  
**Objetivo:** Automatizar atividades repetitivas de portal universitário usando IA  
**Escopo inicial:** Uso pessoal, sem escalonamento comercial  
**Data de início:** 2026-05-12  

---

## Stack Definida

| Camada         | Tecnologia                    |
|----------------|-------------------------------|
| Frontend       | Next.js + Tailwind + shadcn/ui |
| Backend        | Python + FastAPI              |
| Automação      | Playwright (Python)           |
| IA             | OpenAI API → Claude API (futuro) |
| Banco de dados | PostgreSQL                    |
| Fila           | Redis + Celery ou RQ          |
| Logs           | structlog + JSON              |

---

## Fases de Desenvolvimento

### Fase 1 — Discovery + PoC mínima (ATUAL)
- [ ] Reverse engineering do portal
- [ ] Mapeamento do fluxo de login
- [ ] Identificação de APIs internas
- [ ] PoC Playwright: login + navegação + listagem de matérias
- [ ] Logging estruturado básico

### Fase 2 — Core Backend
- [ ] FastAPI com endpoints de controle
- [ ] PostgreSQL integrado (sessões, logs, atividades)
- [ ] Sistema de filas com Celery/RQ
- [ ] Gerenciamento de sessão/cookies persistidos

### Fase 3 — Integração de IA
- [ ] Leitura e parsing de questões
- [ ] Integração OpenAI para resposta automática
- [ ] Prompts especializados por tipo de questão

### Fase 4 — Dashboard
- [ ] Next.js frontend
- [ ] Painel de controle de automações
- [ ] Visualização de logs e resultados

### Fase 5 — Robustez e Expansão
- [ ] RAG para contexto acadêmico
- [ ] Multi-agentes
- [ ] Suporte a múltiplos portais
- [ ] Anti-detection hardening

---

## Arquitetura do MVP (Fase 1)

```
Educator/
├── backend/
│   ├── api/                    # FastAPI routers (fase 2+)
│   ├── automation/
│   │   ├── discovery/          # Scripts de mapeamento do portal
│   │   │   ├── har_capture.py  # Captura tráfego de rede
│   │   │   └── api_mapper.py   # Identifica padrões de API
│   │   ├── flows/
│   │   │   ├── login.py        # Fluxo de autenticação
│   │   │   ├── navigation.py   # Navegação entre matérias
│   │   │   └── activities.py   # Listagem de atividades (fase 2)
│   │   └── utils/
│   │       ├── browser.py      # Factory do browser Playwright
│   │       ├── session.py      # Gerenciamento de cookies/sessão
│   │       ├── retry.py        # Decorador de retry
│   │       └── screenshot.py   # Captura automática em erros
│   ├── core/
│   │   ├── config.py           # Settings via pydantic-settings
│   │   └── logging.py          # structlog setup
│   ├── services/               # Lógica de negócio (fase 2+)
│   ├── schemas/                # Pydantic models
│   └── models/                 # SQLAlchemy models (fase 2+)
├── docs/
│   ├── CONTEXT.md              # Este arquivo
│   ├── ARCHITECTURE.md         # Diagramas e decisões
│   └── PORTAL_MAP.md           # Mapa do portal descoberto
├── logs/                       # Logs estruturados JSON
├── tests/
│   └── automation/
├── scripts/
│   └── run_discovery.py        # Entry point do discovery
└── .env.example
```

---

## Decisões Arquiteturais — ADRs

### ADR-001: Playwright sobre Selenium
**Decisão:** Playwright (Python)  
**Razão:** API async nativa, network interception built-in, auto-wait, screenshot/tracing, melhor suporte a SPAs. Selenium é legado para este caso.  
**Tradeoff:** Playwright é mais pesado, mas os ganhos em resiliência justificam.

### ADR-002: API-first sempre que possível
**Decisão:** Inspecionar e usar APIs internas do portal antes de DOM scraping  
**Razão:** Seletores CSS/XPath quebram a cada redesign. APIs internas mudam com menos frequência e retornam dados estruturados.  
**Como aplicar:** Capturar HAR durante navegação manual e identificar endpoints JSON/REST.

### ADR-003: Sessão persistida em disco
**Decisão:** Salvar state (cookies + localStorage) em arquivo JSON  
**Razão:** Evitar re-login a cada execução; reduzir risco de bloqueio por múltiplos logins.  
**Risco:** Estado pode expirar; implementar refresh automático.

### ADR-004: Logging estruturado desde o início
**Decisão:** structlog com output JSON  
**Razão:** Logs em JSON são indexáveis, filtráveis e prontos para futura integração com Grafana/Loki sem refatoração.

### ADR-005: Configuração 100% por variáveis de ambiente
**Decisão:** pydantic-settings com `.env`  
**Razão:** Sem credenciais hardcoded. Pronto para deploy futuro sem alteração de código.

---

## Estratégia de Reverse Engineering

### Etapa 1 — Inspeção Manual (fazer antes de escrever código)
1. Abrir portal no Chrome com DevTools aberto (aba Network)
2. Executar login manualmente
3. Filtrar por: XHR, Fetch, Doc
4. Identificar:
   - URL e método do login (POST /auth? /login? /api/v1/session?)
   - Payload enviado (form-data, JSON, x-www-form-urlencoded)
   - Headers críticos (CSRF token? X-Requested-With?)
   - Cookies de sessão recebidos
   - Redirects após login
5. Salvar HAR completo: DevTools > Network > botão direito > "Save all as HAR"

### Etapa 2 — Captura Automatizada com Playwright
```python
# Playwright intercepta TODOS os requests em tempo real
# Ver: backend/automation/discovery/har_capture.py
```

### Etapa 3 — Análise dos JS Bundles (se necessário)
- Buscar por strings como `/api`, `fetch(`, `axios.`, `baseURL`
- Usar Source Maps se disponíveis
- Ferramenta: `chrome-har-analyser` ou análise manual

### Indicadores de API interna:
- Responses com `Content-Type: application/json`
- URLs no padrão `/api/`, `/v1/`, `/rest/`
- Requests com Authorization header
- Endpoints que retornam listas estruturadas

---

## Estratégia de Autenticação

### Cenários comuns em portais universitários:

| Tipo | Detecção | Estratégia |
|------|----------|------------|
| Form POST clássico | `<form method="POST">` | Playwright preenche e submete |
| CSRF token | Campo hidden `_token` ou header | Extrair antes do POST |
| SSO/OAuth/SAML | Redirect para IdP externo | Playwright segue redirects |
| JWT | `Authorization: Bearer` nos requests | Capturar e reutilizar token |
| Cookies de sessão | `Set-Cookie` no response do login | Persistir com `context.storage_state()` |

### Fluxo implementado no MVP:
1. Verificar se existe `session.json` válida
2. Se sim: restaurar contexto e validar sessão (request de teste)
3. Se não: executar login via Playwright e salvar estado
4. Em caso de expiração: detectar redirect para login e re-autenticar

---

## Pontos de Risco Identificados

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Portal detecta automação | Média | Alto | User-agent real, delays humanos, headless=false na PoC |
| CSRF token muda por request | Alta | Alto | Capturar token antes de cada submit |
| Sessão expira silenciosamente | Alta | Médio | Health check antes de cada flow |
| Mudança de layout | Alta | Médio | Preferir APIs; usar data-attributes se DOM |
| 2FA ativado | Baixa | Alto | Detectar e pausar para input manual |
| Rate limiting | Média | Médio | Delays configuráveis entre ações |

---

## Variáveis de Ambiente (.env)

```env
# Portal
PORTAL_URL=https://portal.universidade.edu.br
PORTAL_USERNAME=seu_usuario
PORTAL_PASSWORD=sua_senha

# Browser
BROWSER_HEADLESS=false
BROWSER_SLOW_MO=50
BROWSER_TIMEOUT=30000

# Sessão
SESSION_FILE_PATH=./logs/session.json

# Logs
LOG_LEVEL=DEBUG
LOG_FILE=./logs/educator.jsonl
```

---

## Roadmap Semanas 1-4

### Semana 1 — Discovery
- [ ] Inspeção manual do portal (DevTools)
- [ ] Executar `har_capture.py` para mapeamento automatizado
- [ ] Preencher `docs/PORTAL_MAP.md` com endpoints identificados
- [ ] Definir estratégia de auth com base no discovery

### Semana 2 — PoC de Login e Navegação
- [ ] Implementar `login.py` com sessão persistida
- [ ] Implementar `navigation.py` para listagem de matérias
- [ ] Logging estruturado funcionando
- [ ] Retry automático em timeouts

### Semana 3 — Consolidação da PoC
- [ ] Testes de resiliência (forçar expiração de sessão, etc.)
- [ ] Refinar seletores ou migrar para chamadas de API
- [ ] Documentar `PORTAL_MAP.md` completo
- [ ] Review de segurança do código (credenciais, logs)

### Semana 4 — Base do Backend
- [ ] FastAPI com endpoint de trigger manual
- [ ] Estrutura de config com pydantic-settings
- [ ] Preparar integração PostgreSQL (schema inicial)

---

## Log de Progresso

| Data | Evento |
|------|--------|
| 2026-05-12 | Projeto iniciado. Arquitetura Fase 1 definida. |

---

## Perguntas em Aberto

1. Qual é o sistema do portal? (Moodle, TOTVS Educacional, Blackboard, custom?)
2. O portal tem app mobile? (apps móveis geralmente expõem API REST)
3. Existe SSO institucional? (SAML/CAS complica o fluxo de auth)
4. O portal usa SPA (React/Angular/Vue) ou server-rendered?
5. Existe documentação pública ou Swagger do portal?

> **Responder essas perguntas antes de escrever qualquer código de automação.**
