# Changelog — Fork `RaFeltrim/ppchat-api`

Todas as alterações notáveis adicionadas neste fork durante o Workshop BES23 (17/11/2026).

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
