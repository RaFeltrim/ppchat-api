<div align="center">

# PPChat — Assistente Inteligente do PPC de Engenharia de Software

### *Fork com suporte OpenRouter, Fallbacks Multi-Modelo, Anexo de Documentos, Moodle + WhatsApp & Mobile-First · IFSP São Carlos*

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Anthropic_Compat-6366F1?style=for-the-badge)](https://openrouter.ai/)
[![IFSP BES](https://img.shields.io/badge/IFSP-BES_São_Carlos-1F8A4C?style=for-the-badge)](https://www.ifsp.edu.br/)
[![Fork Rafael Feltrim](https://img.shields.io/badge/Fork-Rafael%20Feltrim-0A66C2?style=for-the-badge)](https://github.com/RaFeltrim/ppchat-api)

<p align="center">
  <strong>Assistente conversacional e mapa curricular interativo sobre o Projeto Pedagógico do Curso (PPC) de Bacharelado em Engenharia de Software do IFSP São Carlos, evoluído durante o Workshop BES (17/11/2026) com foco em TokenOps, multi-modelos econômicos, comparação de ementas via documentos e integração Moodle → WhatsApp.</strong>
</p>

[Como Funciona](#-como-funciona) •
[Novidades do Fork](#-novidades-do-fork) •
[Instalação e Uso](#-instalação-e-uso) •
[API REST](#-api-rest) •
[Integrações SUAP & Moodle](#-integrações-suap--moodle) •
[Variáveis de Ambiente](#-configuração-env) •
[Estrutura](#-estrutura-do-projeto)

</div>

---

## Como Funciona

O PPC completo somado ao currículo estruturado ocupa cerca de ~70k–140k tokens dependendo do tokenizador. Em vez de fragmentar o texto via busca vetorial (que falha em perguntas transversais sobre dependências entre semestres), o `ppchat-api` injeta o documento integral (`ppc.md`) e o grafo calculado (`curriculo.json`) no `system` prompt com **Prompt Caching de 1h** (`cache_control`).

```text
PDF ──► texto limpo com [Página N] ────────────────────────────────────┐
   └──► extração estruturada do currículo (JSON validado com Pydantic) │
              └──► CurriculumGraph (cálculo local de dependências) ────┤
                                                                       ▼
                       system prompt = instruções + currículo/grafo + PPC completo (cache 1h)
                                                                       ▼
                        chat multi-turno (OpenRouter / Anthropic) + docs anexos + SUAP
```

1. **Ingestão (`python main.py ingest`):** `PdfLoader` + `TextCleaner` geram `src/data/processed/ppc.md` e `curriculo.json` (já versionados no repositório; se o hash do PDF não mudar, a etapa é pulada).
2. **Grafo (`CurriculumGraph`, custo zero de API):** pré-requisitos diretos/indiretos, o que cada disciplina libera/trava, caminho crítico, gargalos e índice de complexidade estimada (0–10).
3. **Chat (`ChatSession`):** streaming em NDJSON com citação clicável `[Página N]`, menção `@` de disciplinas e controle de fallback automático.

---

## Novidades do Fork

Evoluções implementadas neste fork sobre o projeto base:

| Recurso | Descrição | Arquivos Principais |
| :--- | :--- | :--- |
| **OpenRouter + Multi-Fallback** | Compatibilidade com `ANTHROPIC_BASE_URL` (`https://openrouter.ai/api`), `OPENROUTER_API_KEY` e lista ordenada `FALLBACK_MODELS` no `BetaRefusalFallbackMiddleware`. | `settings.py`, `llm_client.py` |
| **Seletor de Modelos na UI** | Troca em tempo real no composer entre modelos da fronteira de Pareto (`DeepSeek V4.1 Flash`, `GLM 5.3 Flash`, `Gemini 3.5/3.8 Flash`, `Qwen 3.8 27B`). | `index.html`, `app.js`, `chat_service.py` |
| **Anexo de Documentos no Chat** | Upload via `POST /documents/extract` (`.pdf` via PyMuPDF, `.txt`, `.md`, `.csv`, `.json`) para comparar grades/ementas (ex.: USP × IFSP). | `app.py`, `index.html`, `app.js` |
| **Moodle IFSP → WhatsApp** | Aba **Moodle** no drawer (padrão visual do *Meu percurso*), bookmarklet `moodle-export.js` e disparo de alertas via CallMeBot. | `moodle_import.py`, `moodle-export.js`, `app.py` |
| **Reenvio & Devolução ao Chat** | Em erro de API ou cancelamento manual, restaura pergunta e chips `@` no composer com botões `Reenviar` e `Devolver ao chat`. | `app.js` |
| **Mobile-First & Touch** | Hitboxes mínimas de `44px × 44px`, quebra responsiva do composer e fonte `16px` no input para dispositivos móveis. | `styles.css` |
| **Diretriz Anti-Reasoning Leak** | Reforço no prompt de sistema para responder diretamente em português sem expor rascunhos em inglês. | `prompts.py` |

---

## Instalação e Uso

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env-example .env           # Preencha OPENROUTER_API_KEY (ou ANTHROPIC_API_KEY)
```

### Comandos

```bash
python main.py serve                  # API + Interface Web em http://localhost:8000
python main.py serve --port 8080      # Porta customizada
python main.py chat                   # Chat interativo no terminal
python main.py ask "Quais os pré-requisitos de Arquitetura de Software?"
python main.py ingest --force         # Reprocessa o PDF do PPC (apenas se o PDF mudar)
```

---

## API REST

| Método | Rota | Corpo / Parâmetros | Resposta |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Status e total de disciplinas carregadas |
| `GET` | `/curriculum` | — | Currículo estruturado com análise de grafo |
| `GET` | `/pdf` | — | PPC em PDF (suporta `#page=N`) |
| `POST` | `/chat` | `{"question", "history", "disciplinas", "documentos", "model", "perfil", "request_id"}` | `{"answer", "usage"}` |
| `POST` | `/chat/stream` | Mesmo payload de `/chat` | Stream NDJSON (`thinking`, `text`, `done`, `error`) |
| `POST` | `/chat/cancel/{request_id}` | — | `204` — interrompe geração em andamento |
| `POST` | `/documents/extract` | `multipart/form-data` (`file`) | `{"name", "content", "chars", "truncated"}` |
| `POST` | `/aluno/importar` | Payload do bookmarklet SUAP | `{"code"}` para resgate único |
| `GET` | `/aluno/importar/{code}` | — | Dados do aluno (apagados após leitura) |
| `POST` | `/moodle/importar` | `{"tasks", "notify_whatsapp"}` | `{"count", "token", "summary", "whatsapp"}` |
| `GET` | `/moodle/resgatar/{token}` | — | `{"tasks"}` importadas do Moodle |

---

## Integrações SUAP & Moodle

Ambas as integrações usam **bookmarklets locais** que rodam na sessão autenticada do navegador do aluno (sem pedir nem armazenar senhas):

1. **SUAP (`Meu percurso`):** arraste o botão em **Conectar SUAP**, abra o SUAP logado e clique no favorito. Os dados acadêmicos são exibidos na trilha do curso e ficam salvos apenas no `localStorage`.
2. **Moodle (`Moodle`):** arraste o botão em **Conectar Moodle**, acesse `https://moodle.scl.ifsp.edu.br/my/` e clique no favorito. O painel coleta as atividades pendentes, envia para `/moodle/importar`, dispara o alerta no WhatsApp via CallMeBot (se configurado no `.env`) e abre a aba **Moodle** no PPChat.

---

## Configuração (`.env`)

| Variável | Padrão | Uso |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | — | Chave da API do OpenRouter (recomendado) |
| `ANTHROPIC_BASE_URL` | `https://openrouter.ai/api` | Endpoint compatível com Messages API da Anthropic |
| `ANTHROPIC_API_KEY` | — | Chave direta da Anthropic (opcional se usar OpenRouter) |
| `LLM_MODEL` | `deepseek/deepseek-v4.1-flash` | Modelo padrão do chat |
| `EXTRACTION_MODEL` | `google/gemini-3.8-flash` | Modelo usado na extração do PDF |
| `FALLBACK_MODELS` | `["z-ai/glm-5.3-flash", "google/gemini-3.8-flash", "qwen/qwen3.8-27b"]` | Lista ordenada de fallback em caso de recusa |
| `CHAT_EFFORT` / `EXTRACTION_EFFORT` | `low` / `high` | Nível de raciocínio (`low` a `max`) |
| `RATE_LIMIT_PER_HOUR` / `GLOBAL_RATE_LIMIT_PER_HOUR` | `30` / `400` | Limites por IP e global (`0` desativa) |
| `SUAP_ORIGINS` | `["https://suap.ifsp.edu.br", "https://moodle.scl.ifsp.edu.br"]` | Origens permitidas no CORS para os bookmarklets |
| `CALLMEBOT_PHONE` / `CALLMEBOT_APIKEY` | — | Credenciais do CallMeBot para alertas no WhatsApp |

---

## Estrutura do Projeto

```text
ppchat-api/
├── main.py                              # CLI (ingest, chat, ask, serve)
├── render.yaml                          # Blueprint de deploy no Render
├── requirements.txt                     # Dependências Python (inclui python-multipart)
├── CHANGELOG.md                         # Registro das alterações do fork
└── src/
    ├── data/
    │   ├── documents/PPCENGSOFTWARE.pdf # PPC oficial (IFSP São Carlos)
    │   └── processed/                   # ppc.md, curriculo.json, manifest.json
    └── modules/
        ├── ingestion/                   # Extração do PDF e modelo Pydantic do currículo
        ├── knowledge/                   # CurriculumGraph e montagem do KnowledgeBase
        ├── response/                    # ChatSession e SYSTEM_INSTRUCTIONS
        ├── api/                         # FastAPI, rotas SUAP/Moodle, upload e UI em static/
        └── shared/                      # Settings e cliente Anthropic/OpenRouter com fallback
```

---

## Créditos

- **Projeto Original:** [Stanquini](https://github.com/stanquini) e Piovezan
- **Fork & Evoluções (Workshop BES 17/11/2026):** [Rafael Feltrim](https://github.com/RaFeltrim)
