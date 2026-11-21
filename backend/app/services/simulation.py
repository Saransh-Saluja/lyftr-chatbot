"""X-Simulate-Failure header parsing (test hook for failover demos)."""
import litellm

ALLOWED_STATUSES = {429, 500, 502, 503}


class InvalidSimulationHeader(ValueError):
    pass


def parse_simulation_header(value: str | None, valid_key_ids: list[str]) -> dict[str, int]:
    """'key_1=429,key_2=500' -> {'key_1':429,'key_2':500}; '*=429' -> {'*':429}."""
    if value is None or not value.strip():
        return {}
    result: dict[str, int] = {}
    for part in value.split(","):
        key, sep, status = part.strip().partition("=")
        key, status = key.strip(), status.strip()
        if not sep or not key or not status.isdigit():
            raise InvalidSimulationHeader(f"malformed pair: {part.strip()!r}")
        if int(status) not in ALLOWED_STATUSES:
            raise InvalidSimulationHeader(f"status must be one of {sorted(ALLOWED_STATUSES)}")
        if key != "*" and key not in valid_key_ids:
            raise InvalidSimulationHeader(f"unknown key id: {key!r}")
        result[key] = int(status)
    return result


def status_for(simulate: dict[str, int], key_id: str) -> int | None:
    """A specific key entry wins over the '*' wildcard."""
    return simulate.get(key_id, simulate.get("*"))


def build_simulated_error(status: int, model: str) -> Exception:
    """Raise the SAME exception classes LiteLLM raises for real provider failures,
    so simulated failures flow through the exact same except-branch."""
    cls = {
        429: litellm.RateLimitError,
        500: litellm.InternalServerError,
        502: litellm.BadGatewayError,
        503: litellm.ServiceUnavailableError,
    }[status]
    return cls(message=f"simulated provider status {status}", model=model, llm_provider="simulated")
