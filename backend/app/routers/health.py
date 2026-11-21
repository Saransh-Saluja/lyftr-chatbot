import asyncio

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    state = request.app.state
    try:
        await asyncio.to_thread(state.db.ping)
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    keys = len(state.settings.llm_api_keys)
    if keys == 0:
        raise HTTPException(status_code=503, detail="no API keys configured")
    return {
        "status": "ok",
        "keys_configured": keys,
        "cache_enabled": state.llm.cache_enabled,
        # Extra field (contract allows extras): lets the UI show/hide the failover test panel.
        "failure_simulation": state.settings.enable_failure_simulation,
    }
