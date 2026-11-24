"""Controlador bidirecional WhatsApp (OpenClaw + CallMeBot) para o PPChat.

Gerencia o menu interativo no padrão visual do WhatsApp, criação e seleção de conversas
com tag `[MOBILE Conversation:<tópico>]`, histórico compartilhado com `user_data.json`
e controle de standby/desligamento.
"""

from __future__ import annotations

import json
import random
import re
import time
import unicodedata
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

MOBILE_PREFIX = "[MOBILE Conversation:"
STANDBY_DEFAULT_SECONDS = 300

_EMOJI_NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _new_conv_id() -> str:
    base36 = "0123456789abcdefghijklmnopqrstuvwxyz"
    ms = int(time.time() * 1000)
    out = []
    while ms:
        ms, rem = divmod(ms, 36)
        out.append(base36[rem])
    suffix = "".join(random.choice(base36) for _ in range(4))
    return "".join(reversed(out)) + suffix


def _norm(text: str) -> str:
    nfd = unicodedata.normalize("NFD", (text or "").lower().strip())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def format_mobile_title(question: str) -> str:
    """Formata o título da conversa mobile com a tag `[MOBILE Conversation:<tópico>]`."""
    raw = re.sub(r"\s+", " ", (question or "")).strip()
    raw = re.sub(
        r"^(?:(?:oi|ol[aá]|bom dia|boa tarde|boa noite|ei|ppchat)[,!.:;\s-]+)+",
        "",
        raw,
        flags=re.I,
    ).strip()
    topic = raw or "Nova Consulta"
    if len(topic) > 46:
        topic = topic[:43].rstrip(" ,.;:-") + "…"
    return f"{MOBILE_PREFIX}{topic}]"


def md_to_whatsapp(text: str, max_len: int = 3600) -> str:
    """Converte Markdown padrão para formatação nativa do WhatsApp."""
    if not text:
        return "_Sem resposta._"
    out = text.replace("\r\n", "\n")
    # Cabeçalhos Markdown viram negrito destacado
    out = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", out, flags=re.M)
    # **negrito** -> *negrito*
    out = re.sub(r"\*\*(.+?)\*\*", r"*\1*", out)
    # Links [texto](url) -> texto (url)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1 (\2)", out)
    # Limita quebras excessivas
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if len(out) > max_len:
        out = out[: max_len - 24].rstrip() + "\n\n_…(resposta truncada)_"
    return out


def render_offline_menu(pending_question: str = "") -> str:
    """Card WhatsApp exibido quando o servidor local do PPChat está offline."""
    pending_block = ""
    if pending_question and _norm(pending_question) not in {"menu", "/menu", "/ppchat", "ajuda", "/help"}:
        preview = pending_question.strip()
        if len(preview) > 90:
            preview = preview[:87].rstrip() + "…"
        pending_block = f"\n📝 _Sua mensagem ficará na fila e será respondida ao iniciar:_\n> {preview}\n"

    return (
        "╭──────────────────────────╮\n"
        "│  🎓 *PPChat Mobile*      │\n"
        "│  🔴 *Servidor Offline*   │\n"
        "╰──────────────────────────╯\n"
        "\n"
        "O servidor local do PPChat está desligado no momento."
        f"{pending_block}\n"
        "*Deseja iniciar agora via OpenClaw?*\n"
        "*1️⃣* 🚀 Ligar servidor PPChat _(auto-fecha após 5 min em standby)_\n"
        "*0️⃣* ❌ Cancelar\n"
        "\n"
        "_Responda *1* para subir o servidor no computador._"
    )


def render_main_menu(
    active_title: Optional[str],
    total_convs: int,
    idle_remaining_sec: Optional[int] = None,
) -> str:
    """Menu principal no padrão visual WhatsApp quando o PPChat está online."""
    chat_label = active_title or "🆕 Novo chat automático `[MOBILE Conversation: ...]`"
    if idle_remaining_sec is not None:
        mins, secs = divmod(max(0, int(idle_remaining_sec)), 60)
        standby_txt = f"{mins}m {secs:02d}s restantes"
    else:
        standby_txt = "ativo (standby 5 min no modo OpenClaw)"

    return (
        "╭──────────────────────────╮\n"
        "│  🎓 *PPChat Mobile*      │\n"
        "│  🟢 *Servidor Online*    │\n"
        "╰──────────────────────────╯\n"
        "\n"
        f"*💬 Chat ativo:*\n{chat_label}\n\n"
        f"*⏱️ Standby:* {standby_txt}\n\n"
        "*Escolha uma opção (digite o número):*\n"
        "*1️⃣* ➕ Novo chat (`[MOBILE Conversation: ...]`) \n"
        f"*2️⃣* 📂 Selecionar conversa existente ({total_convs})\n"
        "*3️⃣* ℹ️ Status do servidor & contexto\n"
        "*4️⃣* 🛑 Desligar servidor agora\n"
        "\n"
        "_Ou envie sua dúvida diretamente para pesquisar e responder aqui no chat ativo._"
    )


def render_chat_selector(conversations: List[dict], active_id: Optional[str]) -> str:
    """Lista até 10 conversas recentes no padrão WhatsApp para seleção numérica."""
    if not conversations:
        return (
            "📂 *Suas Conversas (0)*\n\n"
            "Ainda não há conversas salvas. Envie qualquer pergunta para criar um novo chat "
            "com a tag `[MOBILE Conversation: ...]`.\n\n"
            "Digite *0* para voltar ao menu."
        )

    lines = [
        "╭──────────────────────────╮",
        "│  📂 *Selecionar Chat*    │",
        "╰──────────────────────────╯",
        "",
    ]
    for idx, conv in enumerate(conversations[:10], start=1):
        badge = _EMOJI_NUMS[idx - 1] if idx <= len(_EMOJI_NUMS) else f"*{idx}.*"
        title = conv.get("title") or "Conversa sem título"
        turns = len(conv.get("history") or [])
        active_mark = " ✅ _(ativo)_" if conv.get("id") == active_id else ""
        lines.append(f"{badge} {title}{active_mark} · _{turns} msg_")

    lines.extend([
        "",
        "*0️⃣* ↩️ Voltar ao menu principal",
        "",
        "_Digite o número da conversa desejada para continuar nela._",
    ])
    return "\n".join(lines)


def load_user_state(state_file: Path) -> dict:
    """Lê o estado local unificado (`user_data.json`)."""
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_user_state(state_file: Path, data: dict) -> None:
    """Persiste o estado local unificado (`user_data.json`)."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_combined_perfil_from_state(state_data: dict) -> Optional[str]:
    """Reconstrói o mesmo `perfil` unificado (IFSP SUAP + Moodle + USP) usado pela Web UI."""
    parts: List[str] = []
    aluno_ctx = (state_data.get("aluno") or {}).get("contexto")
    if aluno_ctx:
        parts.append(f"[IFSP · SUAP]\n{aluno_ctx}")
    moodle_tasks = state_data.get("moodle_tasks") or []
    if isinstance(moodle_tasks, list) and moodle_tasks:
        summary = "\n".join(
            f"- {t.get('course') or 'IFSP'}: {t.get('title') or ''}" + (f" ({t['due']})" if t.get("due") else "")
            for t in moodle_tasks[:25]
        )
        parts.append(f"[IFSP · Moodle - Pendências]\n{summary}")
    usp_ctx = (state_data.get("usp_aluno") or {}).get("contexto")
    if usp_ctx:
        parts.append(f"[USP São Carlos · JupiterWeb & e-Disciplinas]\n{usp_ctx}")
    ufscar_ctx = (state_data.get("ufscar_aluno") or {}).get("contexto")
    if ufscar_ctx:
        parts.append(f"[UFSCar]\n{ufscar_ctx}")
    if not parts:
        return None
    return "\n\n".join(parts)[:29500]


def _find_conv(conversations: List[dict], conv_id: Optional[str]) -> Optional[dict]:
    if not conv_id:
        return None
    return next((c for c in conversations if c.get("id") == conv_id), None)


def _trim_history_for_chat(history: List[dict], limit: int = 30) -> List[dict]:
    out = []
    for turn in history[-limit:]:
        role = turn.get("role")
        if role not in {"user", "assistant"}:
            continue
        out.append({
            "role": role,
            "text": (turn.get("text") or "")[:20000],
            "disciplinas": turn.get("disciplinas") or [],
        })
    return out


async def handle_whatsapp_message(
    state_file: Path,
    sender: str,
    text: str,
    ask_fn: Callable[[str, List[dict], Optional[str], str], Awaitable[str]],
    idle_remaining_sec: Optional[int] = None,
) -> Dict[str, object]:
    """Processa comandos de menu e perguntas vindas do WhatsApp, gravando no histórico unificado."""
    msg = (text or "").strip()
    if not msg:
        msg = "menu"
    norm_msg = _norm(msg)

    state_data = load_user_state(state_file)
    conversations: List[dict] = list(state_data.get("conversations") or [])
    wa_session: dict = dict(state_data.get("whatsapp_session") or {})
    menu_state = wa_session.get("menu_state") or "idle"
    active_conv = _find_conv(conversations, wa_session.get("active_conv_id"))

    def _commit(new_menu_state: Optional[str] = None, active_id: Optional[str] = wa_session.get("active_conv_id")) -> None:
        if new_menu_state is not None:
            wa_session["menu_state"] = new_menu_state
        wa_session["active_conv_id"] = active_id
        wa_session["last_sender"] = sender
        wa_session["updated"] = int(time.time() * 1000)
        state_data["conversations"] = conversations[:60]
        state_data["whatsapp_session"] = wa_session
        save_user_state(state_file, state_data)

    # 1. Menu principal explícito
    if norm_msg in {"menu", "/menu", "/ppchat", "ajuda", "/help", "opcoes"}:
        _commit("main_menu", active_conv.get("id") if active_conv else None)
        return {
            "reply": render_main_menu(active_conv.get("title") if active_conv else None, len(conversations), idle_remaining_sec),
            "action": "menu",
            "conv_id": active_conv.get("id") if active_conv else None,
            "conv_title": active_conv.get("title") if active_conv else None,
        }

    # 2. Navegação dentro do seletor de conversas
    if menu_state == "select_chat":
        if norm_msg in {"0", "voltar", "menu"}:
            _commit("main_menu", active_conv.get("id") if active_conv else None)
            return {
                "reply": render_main_menu(active_conv.get("title") if active_conv else None, len(conversations), idle_remaining_sec),
                "action": "menu",
                "conv_id": active_conv.get("id") if active_conv else None,
                "conv_title": active_conv.get("title") if active_conv else None,
            }
        if re.fullmatch(r"\d{1,2}", norm_msg):
            idx = int(norm_msg) - 1
            visible = conversations[:10]
            if 0 <= idx < len(visible):
                chosen = visible[idx]
                _commit("idle", chosen.get("id"))
                return {
                    "reply": (
                        f"✅ *Conversa selecionada:*\n💬 {chosen.get('title')}\n\n"
                        "_Envie sua próxima mensagem para continuar neste chat (ou digite *menu*)._"
                    ),
                    "action": "selected_chat",
                    "conv_id": chosen.get("id"),
                    "conv_title": chosen.get("title"),
                }
            return {
                "reply": "⚠️ Número fora da lista. Escolha um número válido ou *0* para voltar ao menu.",
                "action": "invalid_option",
                "conv_id": active_conv.get("id") if active_conv else None,
                "conv_title": active_conv.get("title") if active_conv else None,
            }

    # 3. Ações do menu principal (ou atalhos diretos /novo, /chats, /status, /stop)
    if norm_msg in {"/novo", "novo chat", "nova conversa"} or (menu_state == "main_menu" and norm_msg == "1"):
        _commit("awaiting_new_topic", None)
        return {
            "reply": (
                "➕ *Novo Chat Mobile preparado!*\n\n"
                "Envie sua pergunta agora. Ela será salva automaticamente com a tag "
                "`[MOBILE Conversation:<tópico abordado>]`."
            ),
            "action": "new_chat_ready",
            "conv_id": None,
            "conv_title": None,
        }

    if norm_msg in {"/chats", "listar chats", "conversas"} or (menu_state == "main_menu" and norm_msg == "2"):
        _commit("select_chat", active_conv.get("id") if active_conv else None)
        return {
            "reply": render_chat_selector(conversations, active_conv.get("id") if active_conv else None),
            "action": "list_chats",
            "conv_id": active_conv.get("id") if active_conv else None,
            "conv_title": active_conv.get("title") if active_conv else None,
        }

    if norm_msg in {"/status", "status"} or (menu_state == "main_menu" and norm_msg == "3"):
        rem = f"{idle_remaining_sec // 60}m {idle_remaining_sec % 60:02d}s" if idle_remaining_sec is not None else "ativo"
        _commit("idle", active_conv.get("id") if active_conv else None)
        return {
            "reply": (
                "ℹ️ *Status do PPChat Mobile*\n\n"
                "• *Estado:* 🟢 Online (USP + UFSCar + IFSP carregados)\n"
                f"• *Standby (auto-shutdown 5 min):* {rem}\n"
                f"• *Conversas salvas:* {len(conversations)}\n"
                f"• *Chat ativo:* {active_conv.get('title') if active_conv else 'Novo chat sob demanda'}"
            ),
            "action": "status",
            "conv_id": active_conv.get("id") if active_conv else None,
            "conv_title": active_conv.get("title") if active_conv else None,
        }

    if norm_msg in {"/stop", "/desligar", "desligar servidor", "parar servidor"} or (menu_state == "main_menu" and norm_msg in {"4", "0"}):
        if menu_state == "main_menu" and norm_msg == "0":
            _commit("idle", active_conv.get("id") if active_conv else None)
            return {
                "reply": "👌 Menu fechado. Envie sua pergunta normalmente ou digite *menu* quando quiser.",
                "action": "closed_menu",
                "conv_id": active_conv.get("id") if active_conv else None,
                "conv_title": active_conv.get("title") if active_conv else None,
            }
        _commit("idle", active_conv.get("id") if active_conv else None)
        return {
            "reply": "🛑 *Encerrando o servidor PPChat...*\nQuando precisar ligar novamente via OpenClaw, basta enviar uma mensagem aqui.",
            "action": "shutdown",
            "conv_id": active_conv.get("id") if active_conv else None,
            "conv_title": active_conv.get("title") if active_conv else None,
        }

    # 4. Pergunta normal → envia ao ChatSession, salva no histórico compartilhado e responde no padrão WhatsApp
    created_new = active_conv is None
    if created_new:
        active_conv = {
            "id": _new_conv_id(),
            "title": format_mobile_title(msg),
            "history": [],
            "updated": int(time.time() * 1000),
            "source": "whatsapp",
        }
        conversations.insert(0, active_conv)

    prior_history = _trim_history_for_chat(active_conv.get("history") or [])
    perfil = build_combined_perfil_from_state(state_data)
    answer_raw = await ask_fn(msg, prior_history, perfil, "ifsp_bes")

    now_ms = int(time.time() * 1000)
    history = list(active_conv.get("history") or [])
    history.append({"role": "user", "text": msg, "disciplinas": []})
    history.append({"role": "assistant", "text": answer_raw})
    active_conv["history"] = history
    active_conv["updated"] = now_ms

    # Move conversa usada para o topo da lista (igual à Web UI)
    conversations = [active_conv, *[c for c in conversations if c.get("id") != active_conv["id"]]]
    _commit("idle", active_conv["id"])

    formatted = md_to_whatsapp(answer_raw)
    tag_note = "🆕" if created_new else "💬"
    reply = f"{formatted}\n\n_{tag_note} {active_conv['title']} · Digite *menu* para trocar de chat ou encerrar._"
    return {
        "reply": reply,
        "action": "answered",
        "conv_id": active_conv["id"],
        "conv_title": active_conv["title"],
        "created_new": created_new,
    }
