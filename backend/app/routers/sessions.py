import asyncio

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    messages = await asyncio.to_thread(request.app.state.db.get_history, session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": messages}
