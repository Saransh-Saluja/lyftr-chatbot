import asyncio
import time

from fastapi import APIRouter, Header, HTTPException, Request

from app.database import utcnow
from app.schemas import ChatRequest, ChatResponse
from app.services.llm import AllProvidersUnavailable, UpstreamError
from app.services.simulation import InvalidSimulationHeader, parse_simulation_header

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    x_simulate_failure: str | None = Header(default=None),
):
    started = time.perf_counter()
    received_at = utcnow()
    state = request.app.state
    settings, db, llm = state.settings, state.db, state.llm

    # The hook is inert unless explicitly enabled: when off, the header is ignored.
    simulate: dict[str, int] = {}
    if settings.enable_failure_simulation:
        try:
            simulate = parse_simulation_header(x_simulate_failure, [k for k, _ in settings.key_pool])
        except InvalidSimulationHeader as exc:
            raise HTTPException(status_code=422, detail=f"invalid X-Simulate-Failure header: {exc}")

    # One request at a time per session keeps history consistent.
    async with state.session_locks.hold(body.session_id):
        session = await asyncio.to_thread(db.load_session, body.session_id)
        history = session.history if session else []
        system_prompt = body.system_prompt or (session.system_prompt if session else None) or settings.default_system_prompt
        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": body.message}]

        try:
            result = await llm.complete(messages, simulate)
        except AllProvidersUnavailable:
            raise HTTPException(status_code=503, detail="all providers unavailable")
        except UpstreamError:
            raise HTTPException(status_code=502, detail="upstream provider rejected the request")

        latency_ms = int((time.perf_counter() - started) * 1000)
        metadata = {
            "resolution_source": result.source,
            "model": settings.llm_model,
            "latency_ms": latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        }
        # Only now, after a successful answer, is anything written - one transaction.
        await asyncio.to_thread(
            db.save_exchange, body.session_id, body.system_prompt, body.message,
            received_at, result.reply, metadata, utcnow(),
        )
    return {"session_id": body.session_id, "reply": result.reply, "metadata": metadata}
