# Portal Map — UNIC / AVA Educ (Kroton)

> Mapeamento completo — Fase 1 concluída em 2026-05-13.

---

## Arquitetura Completa do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                      UNIC / KROTON ECOSYSTEM                    │
├──────────────────────┬──────────────────────┬───────────────────┤
│  alunodigital.unic.br│  olimpo-api-br.      │  www.avaeduc.     │
│  (ServiceNow SP)     │  kroton.com.br       │  com.br           │
│                      │  (OAuth + Dados      │  (Moodle custom)  │
│  Portal do aluno     │   acadêmicos)        │                   │
│  Financeiro          │                      │  Disciplinas      │
│  Secretaria          │  Auth Server         │  Atividades       │
│  SSO Hub             │  Matrículas          │  Avaliações (quiz)│
└──────────────────────┴──────────────────────┴───────────────────┘
          │                                           │
          └─────── SSO via JWT ────────────────────►  │
                   /auth/pda/login.php?token=JWT
```

---

## Plataformas Identificadas

| Plataforma | URL | Sistema | Papel |
|-----------|-----|---------|-------|
| Portal do Aluno | `alunodigital.unic.br/pda_unic` | ServiceNow Service Portal | Hub, SSO, dados admin |
| Auth Server | `olimpo-api-br.kroton.com.br` | Kroton Olimpo (OAuth 2.0) | Autenticação central |
| **AVA** | **`www.avaeduc.com.br`** | **Moodle** (tema Kroton) | **Disciplinas, atividades, avaliações** |
| AVA API | `api.avaeduc.com.br` | REST API JWT | Acesso programático |

---

## Fluxo de Autenticação — Confirmado

### Fase 1: Login no Portal (UNIC → Kroton Olimpo)
```
GET  alunodigital.unic.br/pda_unic
 → 302 olimpo-api-br.kroton.com.br/loginapi/authorize
 → login.unic.br (SPA 2 passos)
    Passo 1: fill #username (CPF) → submit
    → JS revela #login-pass
    Passo 2: fill #login-pass (senha) → submit
    → POST /loginapi/api/v2/Autenticacao → code
 → GET alunodigital.unic.br/krotonpda?code=XXXX
 → Sessão ServiceNow estabelecida
```

### Fase 2: SSO Portal → AVA Educ (Moodle)
```
GET  alunodigital.unic.br/pda_unic?id=krotonpda_acesso_externo&action=moodle
 → ServiceNow widget gera JWT
 → window.open(avaeduc.com.br/auth/pda/login.php?token=JWT)
 → 301/303 www.avaeduc.com.br/auth/pda/login.php?token=JWT
 → Sessão Moodle estabelecida (MoodleSession cookie)
 → Redirect para www.avaeduc.com.br/
```

---

## Seletores de Login — Confirmados

| Passo | Campo | Seletor | Tipo |
|-------|-------|---------|------|
| 1 | CPF | `#username` | `input[type="text"]` |
| 2 | Senha | `#login-pass` | `input[type="password"]` |
| 1 e 2 | Submit | `button[type="submit"]` | `BUTTON` |

---

## Disciplinas Mapeadas (12 total)

| ID | Nome | Tem Quiz |
|----|------|---------|
| 11208 | Acelere sua Carreira - 2026/1 - Ciência da Computação | Não |
| **10180** | **Algoritmos e Estrutura de Dados Avançado** | **Sim (4 quizzes)** |
| 7136 | Ciências Biológicas | A verificar |
| 8339 | Competências para a Vida | A verificar |
| **10741** | **Desenvolvimento com Low Code** | **Sim (2 quizzes)** |
| 7137 | Matemática | A verificar |
| 7138 | Português | A verificar |
| 816 | Processo Seletivo | Não |
| 8950 | Projeto de Extensão - Ciência da Computação II | A verificar |
| 5008 | Projeto de Software | Não (sem quiz ainda) |
| **11074** | **Segurança da Informação e de Redes** | **Sim (2 quizzes)** |
| **10457** | **Sistemas Digitais e Microprocessadores** | **Sim (2 quizzes)** |

---

## Atividades por Disciplina — Detalhado

### Tipos de atividade encontrados

| Tipo Moodle | Descrição | Relevante para automação |
|-------------|-----------|--------------------------|
| `quiz` | **Avaliações e atividades** | **SIM — PRINCIPAL** |
| `page` | Página de conteúdo HTML | Não (leitura) |
| `url` | Link externo | Não |
| `pde` | Plano de Ensino (custom Kroton) | Não |
| `activityvideo` | Vídeo aula (custom Kroton) | Não |

### Algoritmos e Estrutura de Dados Avançado (id=10180)
| cmid | Tipo | Nome |
|------|------|------|
| 5903038 | quiz | Atividade aula Presencial U1_S1 |
| 5863095 | quiz | Atividade Aula presencial U1_S1 |
| 3813972 | quiz | U1 - Atividade de Aprendizagem |
| 3813973 | quiz | U1 - Avaliação da Unidade |

### Segurança da Informação e de Redes (id=11074)
| cmid | Tipo | Nome |
|------|------|------|
| 5473949 | quiz | U1 - Atividade de Aprendizagem |
| 5473950 | quiz | U1 - Avaliação da Unidade |

### Sistemas Digitais e Microprocessadores (id=10457)
| cmid | Tipo | Nome |
|------|------|------|
| 4368203 | quiz | U1 - Atividade de Aprendizagem |
| 4368204 | quiz | U1 - Avaliação da Unidade |

### Desenvolvimento com Low Code (id=10741)
| cmid | Tipo | Nome |
|------|------|------|
| 4923223 | quiz | U1 - Atividade de Aprendizagem |
| 4923224 | quiz | U1 - Avaliação da Unidade |

---

## APIs do AVA Educ (Moodle)

### Moodle AJAX — Disponível (sesskey obrigatório)
```
POST https://www.avaeduc.com.br/lib/ajax/service.php?sesskey={sesskey}
```
- `sesskey` extraído de `window.M.cfg.sesskey` ou HTML após SSO
- Funções habilitadas: a descobrir por tentativa
- Funções BLOQUEADAS: `core_enrol_get_users_courses`, `core_course_get_contents`

### URLs Moodle Padrão (funcionando via browser)
```
/course/view.php?id={course_id}        → Página da disciplina
/mod/quiz/view.php?id={cmid}           → Tela de entrada do quiz
/mod/quiz/attempt.php?cmid={cmid}      → Tentativa do quiz (questões)
/mod/quiz/summary.php?attempt={id}     → Resumo antes de submeter
/mod/quiz/processattempt.php           → POST de submissão
```

---

## Identificadores do Usuário

| Campo | Valor |
|-------|-------|
| CPF | `05763705173` |
| codigoAluno (Kroton) | `4050521` |
| username (AVA/Moodle) | `fe14236682992a9f553e` |
| sys_user (ServiceNow) | `67796cdc1b5ff91089a332681b4bcb3e` |
| sesskey Moodle | Dinâmico — extrair de `window.M.cfg.sesskey` |

---

## Estratégia de Automação Definida

### Fase 2 — Automação de Quizzes (próxima fase)

**Fluxo completo para responder um quiz:**
```
1. Login portal (Playwright, ~8s)
2. SSO para AVA (Playwright, ~5s)
3. Extrair sesskey de M.cfg
4. Navegar para /mod/quiz/view.php?id={cmid}
5. Verificar se quiz está disponível e tentativas restantes
6. Clicar "Tentar responder agora" → /mod/quiz/attempt.php
7. Ler questões do DOM (texto + alternativas)
8. Enviar para OpenAI API → obter resposta
9. Selecionar alternativa via Playwright
10. Submeter → /mod/quiz/processattempt.php
11. Registrar resultado nos logs
```

**Padrão de questões esperado:**
- Múltipla escolha com 4-5 alternativas
- Texto longo por questão
- Possível timer/limite de tempo

---

## Decisões Arquiteturais para Fase 2

| Decisão | Escolha | Razão |
|---------|---------|-------|
| Leitura de questões | DOM (Playwright) | APIs AJAX bloqueadas para quiz |
| Submissão de respostas | DOM (Playwright) | Mais seguro, simula usuário real |
| Integração IA | OpenAI API (httpx async) | Fora do browser, desacoplado |
| Sessão AVA | Persistir MoodleSession cookie | Evitar SSO a cada execução |

---

## Log de Progresso

| Data | Evento |
|------|--------|
| 2026-05-12 | Projeto iniciado. Arquitetura Fase 1 definida. |
| 2026-05-13 | **Fase 1 concluída.** Login funcionando. 12 disciplinas mapeadas. 10+ quizzes identificados. |
