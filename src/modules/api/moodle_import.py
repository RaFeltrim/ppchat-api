import re
from typing import List, Optional
from urllib.parse import quote_plus
from urllib.request import urlopen

from pydantic import BaseModel, Field


class MoodleTask(BaseModel):
    title: str = Field(max_length=300)
    course: Optional[str] = Field(default=None, max_length=200)
    due: Optional[str] = Field(default=None, max_length=120)
    url: Optional[str] = Field(default=None, max_length=500)


class MoodleImport(BaseModel):
    tasks: List[MoodleTask] = Field(default_factory=list, max_length=100)
    notify_whatsapp: bool = True


def format_moodle_summary(tasks: List[MoodleTask]) -> str:
    if not tasks:
        return "Nenhuma tarefa pendente encontrada no Moodle."
    lines = ["Tarefas e prazos do Moodle (IFSP):"]
    for t in tasks[:20]:
        course = f" [{t.course}]" if t.course else ""
        due = f" — Prazo: {t.due}" if t.due else ""
        lines.append(f"- {t.title}{course}{due}")
    return "\n".join(lines)


def send_whatsapp_callmebot(tasks: List[MoodleTask], phone: str, apikey: str) -> dict:
    """Envia resumo das tarefas do Moodle para o WhatsApp via CallMeBot."""
    if not phone or not apikey:
        return {"sent": False, "reason": "CALLMEBOT_PHONE ou CALLMEBOT_APIKEY não configurados."}
    msg = format_moodle_summary(tasks)
    url = f"https://api.callmebot.com/whatsapp.php?phone={quote_plus(phone)}&text={quote_plus(msg)}&apikey={quote_plus(apikey)}"
    with urlopen(url, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        clean = re.sub(r"<[^>]+>", " ", body).strip()
        if resp.status == 200 and "error" not in clean.lower():
            return {"sent": True, "status": resp.status}
        return {"sent": False, "status": resp.status, "reason": clean[:180] or f"HTTP {resp.status}"}
