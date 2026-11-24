# Changelog — Fork `RaFeltrim/ppchat-api`

Todas as alterações notáveis adicionadas neste fork durante o Workshop BES23 (17–18/11/2026).

## [Unreleased] — 2026-11-24

### Added
- **UFSCar São Carlos (BCC 2025, ENC 2025 e IA 2027 / PPGCC / Especialização DC):** inclusão integral das matrizes curriculares, pré-requisitos e ementas da UFSCar em `usp_jupiter.py`, `#org-select` (`ufscar`) e `#inst-select` (`ufscar_bcc`, `ufscar_enc`, `ufscar_ia_pos`), além dos resumos oficiais dos PPCs da USP (BSI 2026-2, BCI/BCC 4.732h, Estatística).
- **Fluxogramas Completos em Mermaid por Instituto (`build_course_mermaid`, `GET /curriculum/mermaid`, `docs/fluxogramas-mermaid-cursos.md`):** geração compacta de diagramas `flowchart LR` agrupados por instituto (IFSP, USP ICMC/CAASO, UFSCar DC/CCET) e injeção automática em `<fluxogramas_mermaid_ppcs>` no chat para economia de tokens.
- **Motor Semântico de Equivalências & Correção de Visibilidade Multi-Curso:** corrigido o filtro de `render_usp_equivalencias` que ocultava outros cursos e truncava resultados após 25 pares; `compute_equivalences()` agora utiliza sinônimos semânticos e mapeamento validado por ementas (`SSC0959`, `SCC0225`, `SSC0547`, `SSC0900`, `SSC0901`, `UFSCAR-DMOV`, `UFSCAR-ES2`, `UFSCAR-SEGCIB`, `UFSCAR-ASP`).
- **Calendário Oficial de Aluno Especial 2026/2027 & Alerta WhatsApp (`POST /whatsapp/aluno-especial`):** consolidação das datas oficiais do ICMC/USP (CoG 3757) e UFSCar (ProGrad/DiGRA CoG nº 554/2026, PPGCC e Especialização DC Turma 2027) com envio direto via CallMeBot (`send_text_whatsapp_callmebot`).
- **Ponte Bidirecional WhatsApp ↔ OpenClaw ↔ PPChat (`whatsapp_bridge.py`, `scripts/ppchat_openclaw_bridge.py`, `docs/openclaw-whatsapp-bridge.md`):**
  - Recepção de mensagens via OpenClaw (`selfChatMode: true`) com menu visual no padrão WhatsApp, gravação em `user_data.json` sob a tag `[MOBILE Conversation:<tópico>]` e troca/seleção entre chats existentes ou novo chat.
  - Fluxo offline → boot automático do OpenClaw + servidor PPChat (`PPCHAT_IDLE_SHUTDOWN_SECONDS=300`) e desligamento automático após 5 min em standby com aviso CallMeBot.
  - Sincronização/merge de conversas mobile na Web UI (`app.js`).

## [Unreleased] — 2026-11-18

### Added
- **Seletor IFSP / USP no Cabeçalho (`#org-select`) & Seletor Unificado de PPCs no Fluxograma (`#inst-select`):** `#org-select` (`IFSP` | `USP · CAASO`) posicionado à esquerda do botão `Chat`, e `#inst-select` concentrado na barra `#drawer-head` do **Fluxograma** para alternar a visualização entre todos os PPCs (`IFSP · BES`, `USP · BSI`, `USP · BCI/BCC` e `USP · Estatística`), persistidos em `localStorage`.
- **Sincronização Autenticada JupiterWeb + e-Disciplinas USP (`GET /usp/aluno`, `POST /usp/aluno/sync`):**
  - Coleta automática no JupiterWeb da **Grade Horária** (`GradeHorariaControleDWR.obterGradeHoraria`, disciplinas `cursando` como `SSC0124`) e do **Histórico Escolar Final em PDF** (`EmissaoHEControleDWR` + `historicoescolarListar` via `PyMuPDF`, disciplinas `concluida` como `SSC0961` com nota e frequência).
  - Login SAML automático via `idpcafe.usp.br` no **e-Disciplinas USP** (`edisciplinas.usp.br`), listando disciplinas matriculadas, tarefas (`/mod/assign`, `/mod/quiz`) e materiais (`/mod/resource`, `/mod/url`).
  - Exibição completa nas abas **Fluxograma** (badge/cor de concluída/cursando e notas + inclusão automática das cursadas em todas as grades USP), **Meu Percurso** (trilha interativa `#trail` + `#stop-detail` dos semestres cursados/atuais na USP) e **Moodle** (`renderUspMoodle` combinando histórico e e-Disciplinas com repositórios locais em `Downloads` como `APOO - USP` e `Web e Mobile - USP` + links GitHub).
  - Persistência e cache local deduplicado (`usp_aluno` em `/local/state` e `ppchat-usp-aluno-v1` com proteção contra chamadas simultâneas).
  - Auto-login e sincronização automática em segundo plano na inicialização do servidor (`_auto_sync_usp_on_startup` em `app.py` via `USP_USER` / `USP_PASSWORD`).
- **Contexto Unificado Multi-Institucional & Evidências Práticas do GitHub (`<repositorios_disciplinas>`):**
  - Contexto unificado no agente (`combinedPerfilContext` em `app.js`, `<dados_usp>` em `chat_service.py`, `self.usp_aluno` em `knowledge_base.py` e `prompts.py`) enviando simultaneamente SUAP/Moodle IFSP, JupiterWeb/e-Disciplinas USP e gancho futuro para UFSCar.
  - `render_repo_evidences` (`knowledge_base.py`, `chat_service.py`, `prompts.py`, `github_student.py`) ranqueia todos os repositórios de estudo por palavras-chave da pergunta (sem limite fixo de quantidade) e injeta árvore de arquivos e README resumido no chat.
- **Suíte de Testes QA & Cobertura (`tests/test_ppchat_suite.py`, `tests/run_qa_coverage.py`):** testes unitários, de integração, contrato de API, fumaça e carga/performance com medição de cobertura.
  - **Roteamento FinOps `SLM-First` (`model_router.py` + `docs/slm-finops-nanochat.md`):** opção `Auto (SLM-First FinOps)` em `#model-select`, configurações `SLM_FIRST_ENABLED` / `SLM_MODEL` / `SLM_BASE_URL` e roteamento automático entre Tier 0 (`SLM_MODEL`, esforço `low`) e Tier High (`LLM_MODEL`).
- **Integração USP São Carlos (CAASO) — JupiterWeb (`usp_jupiter.py`):**
  - Sincronização das grades curriculares do ICMC/USP São Carlos (`55051/4` BSI, `55041/0` BCI/BCC e `55071/4` Estatística e Ciência de Dados) em `src/data/processed/usp_curriculos.json`.
  - Consulta e cache local de ementas/conteúdo programático do JupiterWeb em `GET /usp/disciplina/{sgldis}` (`src/data/processed/usp_ementas.json`).
  - Motor automático de equivalência IFSP BES ↔ USP São Carlos (`GET /usp/equivalencias` e enriquecimento em `GET /curriculum?inst=...` e no contexto do agente em `chat_service.py` / `prompts.py`).
  - Gerador de minuta formal de **Requerimento de Aproveitamento de Estudos (SUAP)** em `POST /usp/requerimento`, acessível diretamente pelo card de equivalência no Fluxograma (`openUspRequerimentoModal` com cópia rápida e refinamento no chat).
- Variáveis opcionais `USP_USER` e `USP_PASSWORD` adicionadas a `settings.py` e `.env-example`, e origem `https://uspdigital.usp.br` adicionada a `suap_origins`.

### Fixed
- Guardas em `studentStatus`, `gradeTag`, `renderCourseInfo` e `setAluno` para aplicar o overlay de status do SUAP apenas quando `state.inst === "ifsp_bes"`, preservando o contexto do aluno ao navegar pelas grades da USP.
- Movida a declaração de `RequerimentoRequest` em `src/modules/api/app.py` para fora dos validadores de `ChatRequest`.

## [Unreleased] — 2026-11-17

### Added
- Suporte a **OpenRouter** via `OPENROUTER_API_KEY` e `ANTHROPIC_BASE_URL` em `settings.py` e `llm_client.py`.
- Suporte a lista de múltiplos modelos de fallback (`FALLBACK_MODELS`) no `BetaRefusalFallbackMiddleware`.
- Seletor dinâmico de modelos na barra de composição (`#model-select` em `index.html`, `app.js` e `ChatRequest.model`).
- Upload e extração de documentos no chat (`POST /documents/extract` com suporte a `.pdf`, `.txt`, `.md`, `.csv` e `.json`; requer `python-multipart`).
- Integração **Moodle IFSP → PPChat → WhatsApp (CallMeBot)**:
  - `src/modules/api/moodle_import.py` e rotas `POST /moodle/importar` e `GET /moodle/resgatar/{token}`.
  - Bookmarklet `src/modules/api/static/moodle-export.js` com painel flutuante seguindo o padrão do `suap-export.js`.
  - Aba **Moodle** no drawer (`#view-moodle`) seguindo o padrão visual de **Meu percurso**.
- Sistema de reenvio/devolução da mensagem ao composer (`↻ Reenviar` e `✎ Devolver ao chat`) em erro de API ou cancelamento.
- Regras **Mobile-First** em `styles.css` (hitboxes `44px × 44px`, layout responsivo do composer e `16px` no input).

### Changed
- `CHAT_EFFORT` ajustado para `low` e diretriz em `prompts.py` reforçada para evitar exposição de raciocínio interno em inglês e orientar importação via SUAP.
- CORS em `app.py` garantindo inclusão de `https://moodle.scl.ifsp.edu.br`.
- `.env-example` e `requirements.txt` atualizados.

### Polimento & Expansão (17/11/2026 - noite)
- **Persistência local em disco (`GET/POST /local/state`):** salva e restaura automaticamente dados do SUAP, tarefas do Moodle e conversas em `src/data/local/user_data.json`.
- **Launcher nativo `PPChat.exe`:** inicialização automática do servidor em segundo plano e abertura no navegador padrão.
- **Filtros inteligentes do Moodle (`moodle-export.js` e `app.js`):** ignora tarefas já enviadas (`/mod/assign/`), questionários já avaliados (`/mod/quiz/`) e restringe a visualização às disciplinas cursadas no SUAP.
- **Aba Moodle no padrão Fluxograma:** cards `.node` clicáveis + painel lateral `#moodle-info` integrado aos repositórios GitHub e arquivos locais em `Downloads` (`GET /moodle/repos`, `GET /moodle/file`, com proteção `is_relative_to` e layout responsivo no mobile).
- **Base oficial Drive IFSP (`ifsp_drive.py` + `ifsp_docs.json` + `GET /ifsp-docs`):** 20 formulários e manuais DDGA/SUAP indexados com injeção sob demanda (TokenOps).
