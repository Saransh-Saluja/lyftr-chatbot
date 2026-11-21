"""Configuration: everything comes from environment variables (12-factor style)."""
import os
from dataclasses import dataclass

# Avoid a network fetch of LiteLLM's model-price map at import time. The bundled
# local copy is enough for us and makes startup deterministic offline/in Docker.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(v.strip() for v in (value or "").split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    llm_api_keys: tuple[str, ...]
    llm_model: str
    llm_api_base: str | None
    database_url: str
    allowed_origins: tuple[str, ...]
    enable_failure_simulation: bool
    default_system_prompt: str
    llm_timeout_seconds: float
    cache_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(
            llm_api_keys=_csv(e("LLM_API_KEYS")),
            llm_model=e("LLM_MODEL", "gemini/gemini-3.5-flash-lite"),
            llm_api_base=e("LLM_API_BASE") or None,
            database_url=e("DATABASE_URL", "sqlite:///./data/app.db"),
            # A trailing slash is a classic CORS mistake ("https://x.app/" never equals the
            # browser's Origin "https://x.app"), so strip it here instead of failing silently.
            allowed_origins=tuple(o.rstrip("/") for o in _csv(e("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"))),
            enable_failure_simulation=_bool(e("ENABLE_FAILURE_SIMULATION"), False),
            default_system_prompt=e("DEFAULT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            llm_timeout_seconds=float(e("LLM_TIMEOUT_SECONDS", "30")),
            cache_ttl_seconds=int(e("CACHE_TTL_SECONDS", "3600")),
        )

    @property
    def key_pool(self) -> list[tuple[str, str]]:
        """Stable ids by position: key_1, key_2, ... (never logged or returned)."""
        return [(f"key_{i}", k) for i, k in enumerate(self.llm_api_keys, start=1)]
