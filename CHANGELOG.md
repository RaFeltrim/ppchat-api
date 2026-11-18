# Changelog — Fork `RaFeltrim/ppchat-api`

Todas as alterações notáveis adicionadas neste fork durante o Workshop BES23 (17–18/11/2026).

## [Unreleased] — 2026-11-18

### Added
- **Seletor Multi-Instituição no Cabeçalho (`#inst-select`):** menu selecionável à esquerda do botão `Chat` alternando entre `IFSP · BES` (`ifsp_bes`), `USP · BSI (CAASO)` (`usp_bsi`), `USP · BCI (CAASO)` (`usp_bci`) e `USP · Estatística (CAASO)` (`usp_est`), persistido em `localStorage("ppchat_inst")`.
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
