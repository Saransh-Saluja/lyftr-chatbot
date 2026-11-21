"""LLM gateway: ordered key failover + LiteLLM response cache.

Why an explicit loop instead of litellm.Router fallbacks?
The contract needs `key_id` (who answered) and `fallback_attempts` (how many keys
failed first). A Router hides per-attempt outcomes, so we own the loop and use
LiteLLM for what it is good at: the provider call, exception normalisation,
usage reporting and the cache.
"""
import hashlib
import json
import logging
from dataclasses import dataclass

import litellm
from litellm import Cache

from app.config import Settings
from app.services.locks import KeyedLock
from app.services.simulation import build_simulated_error, status_for

log = logging.getLogger("app.llm")
litellm.suppress_debug_info = True

LIVE = "LIVE_INFERENCE"
CACHE = "LLM_CACHE"

# Errors that mean "this KEY (or provider moment) is the problem -> try the next key".
_FAILOVER_TYPES = (
    litellm.RateLimitError,          # 429 / quota exhausted
    litellm.Timeout,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,  # 503
    litellm.InternalServerError,      # 500
    litellm.BadGatewayError,          # 502
    litellm.AuthenticationError,      # revoked / invalid key
    litellm.PermissionDeniedError,
)
_FAILOVER_STATUSES = {401, 402, 403, 408, 429}


def is_failover_error(exc: Exception) -> bool:
    if isinstance(exc, _FAILOVER_TYPES):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status >= 500 or status in _FAILOVER_STATUSES)


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed with a failover-class error."""


class UpstreamError(Exception):
    """Provider rejected the request in a way another key cannot fix (e.g. HTTP 400)."""


@dataclass
class LLMResult:
    reply: str
    source: str
    key_id: str | None
    fallback_attempts: int
    input_tokens: int
    output_tokens: int


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.llm_model
        self.keys = settings.key_pool
        self._locks = KeyedLock()
        # LiteLLM's built-in in-memory cache. Fresh instance per service (=per app).
        self.cache = Cache(type="local", default_in_memory_ttl=settings.cache_ttl_seconds)
        litellm.cache = self.cache

    @property
    def cache_enabled(self) -> bool:
        return litellm.cache is self.cache

    def _lock_id(self, messages: list[dict]) -> str:
        raw = json.dumps([self.model, messages], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def complete(self, messages: list[dict], simulate: dict[str, int] | None = None) -> LLMResult:
        simulate = simulate or {}
        if simulate:
            # Simulated requests neither read nor write the cache, so a failover
            # demo is deterministic and cannot pollute later normal requests.
            return await self._run(messages, simulate)
        # Identical in-flight requests queue up: the 2nd one then hits the cache
        # instead of paying for a duplicate provider call.
        async with self._locks.hold(self._lock_id(messages)):
            return await self._run(messages, simulate)

    async def _run(self, messages: list[dict], simulate: dict[str, int]) -> LLMResult:
        failed = 0
        for key_id, api_key in self.keys:
            try:
                resp = await self._attempt(key_id, api_key, messages, simulate)
            except Exception as exc:  # noqa: BLE001 - classified below
                status = getattr(exc, "status_code", None)
                if is_failover_error(exc):
                    failed += 1
                    log.warning("%s failed (%s, status=%s); failing over", key_id, type(exc).__name__, status)
                    continue
                log.error("%s non-retryable error (%s, status=%s)", key_id, type(exc).__name__, status)
                raise UpstreamError from None  # never leak provider text (may echo secrets)
            return await self._build_result(resp, key_id, failed, messages, bool(simulate))
        raise AllProvidersUnavailable

    async def _attempt(self, key_id: str, api_key: str, messages: list[dict], simulate: dict[str, int]):
        sim_status = status_for(simulate, key_id)
        if sim_status is not None:
            # Same exception classes as a real failure -> same except-branch above.
            raise build_simulated_error(sim_status, self.model)
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            api_key=api_key,
            num_retries=0,  # WE own retries/failover, LiteLLM must not hide attempts
            timeout=self.settings.llm_timeout_seconds,
        )
        if self.settings.llm_api_base:
            kwargs["api_base"] = self.settings.llm_api_base
        if simulate:
            # LiteLLM per-call cache controls: skip the cache READ and the WRITE.
            kwargs["cache"] = {"no-cache": True, "no-store": True}
        return await litellm.acompletion(**kwargs)

    async def _build_result(self, resp, key_id: str, failed: int, messages: list[dict], simulated: bool) -> LLMResult:
        reply = (resp.choices[0].message.content or "").strip()
        if not reply:
            raise UpstreamError
        cache_hit = resp._hidden_params.get("cache_hit") is True
        if not cache_hit and not simulated:
            # LiteLLM writes the cache in a background task (~100 ms lag in 1.110.2),
            # so an immediate repeat would miss. Write through explicitly.
            await self.cache.async_add_cache(resp, model=self.model, messages=messages)
        usage = resp.usage
        in_tok, out_tok = int(usage.prompt_tokens or 0), int(usage.completion_tokens or 0)
        return LLMResult(
            reply=reply,
            source=CACHE if cache_hit else LIVE,
            key_id=None if cache_hit else key_id,
            fallback_attempts=0 if cache_hit else failed,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
