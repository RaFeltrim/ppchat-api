# Integração Bidirecional WhatsApp ↔ OpenClaw ↔ PPChat

## Visão Geral da Arquitetura

O **CallMeBot** (`api.callmebot.com`) é unidirecional (apenas notificações de saída). Para permitir que mensagens enviadas por você no WhatsApp cheguem ao PPChat, pesquisem nos PPCs/SUAP/USP/UFSCar/GitHub e voltem no WhatsApp — inclusive ligando e desligando o servidor sob demanda — o fluxo utiliza o **OpenClaw Gateway** já instalado localmente (`~/.openclaw/openclaw.json`, porta `18789`, canal `whatsapp` com `selfChatMode: true`):

```text
WhatsApp (Você)
   │
   ▼
OpenClaw Gateway (:18789 · channels.whatsapp)
   │ exec: python scripts/ppchat_openclaw_bridge.py --sender "$SENDER" --text "$TEXT"
   ▼
scripts/ppchat_openclaw_bridge.py
   ├── [PPChat :8000 ONLINE] ──► POST /whatsapp/incoming ──► ChatSession.ask() + user_data.json
   │                                                          └── salva `[MOBILE Conversation:<tópico>]`
   └── [PPChat :8000 OFFLINE] ─► Exibe menu padrão WhatsApp ("1️⃣ Ligar servidor PPChat")
                                  └── Ao receber "1":
                                      1. Garante OpenClaw Gateway (:18789) ativo
                                      2. Inicia `python main.py serve` com PPCHAT_IDLE_SHUTDOWN_SECONDS=300
                                      3. Responde automaticamente à pergunta que estava pendente
```

## Ciclo de Standby Automático (5 minutos)
- Todo servidor iniciado pelo bridge define `PPCHAT_IDLE_SHUTDOWN_SECONDS=300`.
- Um middleware em `src/modules/api/app.py` atualiza `_last_activity_ts` a cada requisição ativa (chat, WhatsApp, fluxo, Moodle).
- Chamadas de monitoramento (`GET /health`, `GET /whatsapp/status`) **não** resetam o relógio de standby.
- Após **5 minutos (300s)** sem atividade, o watchdog encerra o servidor graciosamente e envia notificação via **CallMeBot** (`💤 PPChat encerrado automaticamente após 5 min em standby...`).

## Menu Visual WhatsApp & Conversas `[MOBILE Conversation: ...]`
Envie **`menu`** a qualquer momento pelo WhatsApp:
- **1️⃣ Novo chat:** abre uma conversa limpa; a próxima pergunta cria automaticamente uma entrada em `src/data/local/user_data.json` com título **`[MOBILE Conversation:<tópico>]`**, visível na barra lateral **Recentes** da interface Web.
- **2️⃣ Selecionar conversa existente:** lista até 10 conversas recentes numeradas (`1️⃣`..`🔟`), permitindo continuar um chat da Web ou outro chat mobile.
- **3️⃣ Status:** mostra se está Online, o chat ativo e o tempo restante até o auto-shutdown.
- **4️⃣ Desligar servidor agora:** encerra imediatamente a instância local.

## Comando para Configurar no Agente do OpenClaw
Configure uma instrução/skill no seu agente do OpenClaw (`selfChatMode: true`) para que mensagens destinadas ao PPChat executem:

```bash
python "c:\Users\Rafael Feltrim\Downloads\Workshop BES23\ppchat-api\scripts\ppchat_openclaw_bridge.py" --sender "+5519997775596" --text "<TEXTO_DO_USUARIO>"
```

E retornem exatamente o `stdout` impresso pelo script ao usuário no WhatsApp.
