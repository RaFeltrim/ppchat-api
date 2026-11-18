"""Roteador FinOps SLM-First para o PPChat (Tier 0 SLM Local/Econômico vs. Tier High LLM)."""

from dataclasses import dataclass
from typing import Literal, Optional

from src.modules.shared.services.settings import Effort, Settings

Tier = Literal["slm", "llm", "manual"]

_HIGH_COMPLEXITY_TRIGGERS = (
    "planej",
    "plano",
    "semestre a semestre",
    "equival",
    "aproveit",
    "requerimento",
    "compar",
    "reprov",
    "trava",
    "cadeia",
    "ufscar",
    "aluno especial",
    "justificativa",
    "arquitet",
)


@dataclass(frozen=True)
class RouteDecision:
    tier: Tier
    model: str
    effort: Effort
    reason: str
    use_local_slm: bool = False


def route_inference(
    question: str,
    *,
    has_docs: bool = False,
    history_len: int = 0,
    requested_model: Optional[str] = None,
    settings: Settings,
) -> RouteDecision:
    """Decide entre SLM especialista (Tier 0) e LLM generalista (Tier High)."""
    req = (requested_model or "").strip()
    if req and req.lower() != "auto":
        return RouteDecision(
            tier="manual",
            model=req,
            effort=settings.chat_effort,
            reason="modelo selecionado manualmente na interface",
        )

    if not settings.slm_first_enabled:
        return RouteDecision(
            tier="llm",
            model=settings.llm_model,
            effort=settings.chat_effort,
            reason="roteamento SLM-First desativado nas configurações",
        )

    q_low = question.lower()
    is_complex = (
        has_docs
        or history_len >= 4
        or len(question) > 220
        or any(trigger in q_low for trigger in _HIGH_COMPLEXITY_TRIGGERS)
    )
    if is_complex:
        return RouteDecision(
            tier="llm",
            model=settings.llm_model,
            effort=settings.chat_effort,
            reason="tarefa complexa (anexos, planejamento, equivalência ou multi-turno)",
        )

    return RouteDecision(
        tier="slm",
        model=settings.slm_model,
        effort="low",
        reason="consulta objetiva/FAQ roteada para SLM econômico (FinOps)",
        use_local_slm=bool(settings.slm_base_url),
    )
