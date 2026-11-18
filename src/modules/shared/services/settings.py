from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[4]

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Se vazia, o SDK procura ANTHROPIC_API_KEY no ambiente ou um login do `ant auth login`
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    anthropic_base_url: Optional[str] = "https://openrouter.ai/api"

    llm_model: str = "deepseek/deepseek-v4.1-flash"
    # A extração roda uma vez por PDF; vale usar um modelo mais forte que o do chat
    extraction_model: Optional[str] = "google/gemini-3.8-flash"
    # Usado só se o modelo principal recusar a requisição (middleware de fallback do SDK)
    fallback_model: str = "z-ai/glm-5.3-flash"
    fallback_models: List[str] = [
        "z-ai/glm-5.3-flash",
        "google/gemini-3.8-flash",
        "qwen/qwen3.8-27b",
    ]

    # Esforço de raciocínio: chat pode ser "medium"; extração estruturada merece mais
    chat_effort: Effort = "medium"
    extraction_effort: Effort = "high"
    max_output_tokens: int = 64000

    # Roteamento FinOps SLM-First (Tier 0 local/econômico vs. Tier High LLM)
    slm_first_enabled: bool = True
    slm_model: str = "qwen/qwen3.8-27b"
    slm_base_url: Optional[str] = None  # Ex.: http://127.0.0.1:1234/v1 (LM Studio) ou http://127.0.0.1:11434/v1 (Ollama)

    # Proteção dos créditos da API quando o site é público (0 desliga)
    rate_limit_per_hour: int = 30  # perguntas por IP
    global_rate_limit_per_hour: int = 400  # teto para o site inteiro, vale mesmo se alguém forjar o IP

    # Origens do SUAP, Moodle e JupiterWeb USP de onde os bookmarklets podem enviar dados (CORS)
    suap_origins: List[str] = ["https://suap.ifsp.edu.br", "https://moodle.scl.ifsp.edu.br", "https://uspdigital.usp.br"]

    # Credenciais USP (opcional, uso local para JupiterWeb/aluno especial)
    usp_user: Optional[str] = None
    usp_password: Optional[str] = None

    # CallMeBot (alertas no WhatsApp para tarefas do Moodle)
    callmebot_phone: Optional[str] = None
    callmebot_apikey: Optional[str] = None

    # Arquivos
    pdf_path: Path = ROOT_DIR / "src" / "data" / "documents" / "PPCENGSOFTWARE.pdf"
    processed_dir: Path = ROOT_DIR / "src" / "data" / "processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
