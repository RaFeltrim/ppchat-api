"""Supervisor OpenClaw <-> PPChat para mensagens recebidas via WhatsApp.

Uso típico pelo agente/canal WhatsApp do OpenClaw:
    python scripts/ppchat_openclaw_bridge.py --sender "+5519997775596" --text "<mensagem>"

Fluxo:
1. Se o servidor PPChat estiver online (`GET /health`), encaminha a mensagem para
   `POST /whatsapp/incoming` e imprime a resposta formatada no padrão WhatsApp.
2. Se estiver offline:
   - Na primeira mensagem, grava a pergunta como pendente e exibe o menu de boot.
   - Se o usuário responder `1` (ou enviar `/start` / `ligar ppchat`), garante que o
     OpenClaw Gateway (:18789) esteja ativo, sobe `python main.py serve` em background
     com standby automático de 5 minutos (`PPCHAT_IDLE_SHUTDOWN_SECONDS=300`) e já
     processa a mensagem pendente assim que o `/health` responder 200.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.modules.api.moodle_import import send_text_whatsapp_callmebot
from src.modules.api.whatsapp_bridge import (
    _norm,
    load_user_state,
    render_main_menu,
    render_offline_menu,
    save_user_state,
)
from src.modules.shared.services.settings import get_settings

STATE_FILE = ROOT_DIR / "src" / "data" / "local" / "user_data.json"


def _is_port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_ppchat_online(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ensure_openclaw_gateway() -> bool:
    """Garante que o OpenClaw Gateway (:18789) esteja ativo no computador."""
    if _is_port_open("127.0.0.1", 18789):
        return True
    clawd_entry = Path.home() / "clawd" / "node_modules" / "openclaw" / "dist" / "index.js"
    gw_cmd = Path.home() / ".openclaw" / "gateway.cmd"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if clawd_entry.exists():
        cmd = ["node", str(clawd_entry), "gateway", "--port", "18789"]
        cwd = str(clawd_entry.parents[3])
    elif gw_cmd.exists():
        cmd = ["cmd.exe", "/c", str(gw_cmd)]
        cwd = str(gw_cmd.parent)
    else:
        return False
    subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _is_port_open("127.0.0.1", 18789):
            return True
        time.sleep(0.4)
    return _is_port_open("127.0.0.1", 18789)


def _start_ppchat_server(base_url: str, standby_seconds: int = 300) -> bool:
    """Inicia o servidor local do PPChat em background com watchdog de standby."""
    env = os.environ.copy()
    env["PPCHAT_IDLE_SHUTDOWN_SECONDS"] = str(max(60, standby_seconds))
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [sys.executable, "main.py", "serve"],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _is_ppchat_online(base_url, timeout=1.5):
            return True
        time.sleep(0.5)
    return False


def _post_incoming(base_url: str, sender: str, text: str, deliver_callmebot: bool = False) -> dict:
    body = json.dumps({"sender": sender, "text": text, "deliver_callmebot": deliver_callmebot}).encode("utf-8")
    req = Request(
        f"{base_url.rstrip('/')}/whatsapp/incoming",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def process_bridge_message(
    sender: str,
    text: str,
    base_url: str = "http://127.0.0.1:8000",
    standby_seconds: int = 300,
    deliver_callmebot: bool = False,
    state_file: Path = STATE_FILE,
    starter_fn=None,
) -> str:
    """Executa o fluxo completo Online / Offline + Auto-Start OpenClaw e retorna a mensagem de resposta."""
    msg = (text or "").strip() or "menu"
    norm_msg = _norm(msg)

    if _is_ppchat_online(base_url):
        res = _post_incoming(base_url, sender, msg, deliver_callmebot=deliver_callmebot)
        return str(res.get("reply") or "")

    state_data = load_user_state(state_file)
    wa_session = dict(state_data.get("whatsapp_session") or {})
    awaiting_start = wa_session.get("menu_state") == "awaiting_start"
    start_triggers = {"/start", "start ppchat", "ligar ppchat", "iniciar ppchat"}

    if norm_msg in start_triggers or (awaiting_start and norm_msg in {"1", "iniciar", "ligar", "start", "sim", "subir"}):
        pending_q = (wa_session.get("pending_question") or "").strip()
        gw_ok = _ensure_openclaw_gateway() if starter_fn is None else True
        srv_ok = starter_fn(base_url, standby_seconds) if starter_fn else _start_ppchat_server(base_url, standby_seconds)
        if not srv_ok:
            reply = "⚠️ Não foi possível iniciar o servidor local do PPChat dentro de 30 segundos."
        else:
            wa_session["menu_state"] = "idle"
            wa_session["pending_question"] = ""
            state_data["whatsapp_session"] = wa_session
            save_user_state(state_file, state_data)

            gw_note = "OpenClaw Gateway ativo" if gw_ok else "OpenClaw CLI local"
            header = f"🟢 *PPChat iniciado via {gw_note}!*\n_Standby automático: {standby_seconds // 60} min sem uso._\n\n"
            if pending_q and _is_ppchat_online(base_url):
                ans = _post_incoming(base_url, sender, pending_q, deliver_callmebot=False)
                reply = header + str(ans.get("reply") or "")
            elif _is_ppchat_online(base_url):
                convs = state_data.get("conversations") or []
                reply = header + render_main_menu(None, len(convs), standby_seconds)
            else:
                reply = header + "Servidor iniciado. Já pode enviar sua dúvida!"
    elif awaiting_start and norm_msg in {"0", "cancelar", "nao"}:
        wa_session["menu_state"] = "idle"
        wa_session["pending_question"] = ""
        state_data["whatsapp_session"] = wa_session
        save_user_state(state_file, state_data)
        reply = "❌ Inicialização cancelada. O servidor permanece offline."
    else:
        wa_session["menu_state"] = "awaiting_start"
        if norm_msg not in {"menu", "/menu", "/ppchat", "ajuda", "/help"}:
            wa_session["pending_question"] = msg
        wa_session["last_sender"] = sender
        wa_session["updated"] = int(time.time() * 1000)
        state_data["whatsapp_session"] = wa_session
        save_user_state(state_file, state_data)
        reply = render_offline_menu(wa_session.get("pending_question") or "")

    if deliver_callmebot:
        try:
            s = get_settings()
            send_text_whatsapp_callmebot(reply, s.callmebot_phone or sender, s.callmebot_apikey or "")
        except Exception:
            pass
    return reply


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge OpenClaw/WhatsApp <-> PPChat")
    parser.add_argument("--sender", default="+5519997775596", help="Telefone remetente no WhatsApp")
    parser.add_argument("--text", required=True, help="Texto recebido do WhatsApp")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="URL base do servidor PPChat")
    parser.add_argument("--standby-seconds", type=int, default=300, help="Tempo em standby antes de encerrar")
    parser.add_argument("--callmebot", action="store_true", help="Espelhar resposta também via CallMeBot")
    args = parser.parse_args(argv)
    print(
        process_bridge_message(
            sender=args.sender,
            text=args.text,
            base_url=args.url,
            standby_seconds=args.standby_seconds,
            deliver_callmebot=args.callmebot,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
