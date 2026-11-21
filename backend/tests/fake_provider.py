"""A tiny OpenAI-compatible fake provider used ONLY for offline testing.

It lets us exercise LiteLLM's real HTTP/caching/exception code paths without
network access or real API keys. It is NOT a substitute for a real-provider
check (see README "Verification").

Behaviour is controlled per API key:
  * key starting with "fail429" -> HTTP 429
  * key starting with "fail500" -> HTTP 500
  * key starting with "fail400" -> HTTP 400 (not a failover case)
  * any other key               -> 200 with deterministic text + usage
"""
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def make_app(state: dict) -> FastAPI:
    app = FastAPI()
    state.setdefault("calls", [])  # list of (api_key, last_user_message)
    state.setdefault("delay", 0.0)
    state.setdefault("requests", [])  # full message lists, for multi-turn assertions

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        auth = request.headers.get("authorization", "")
        key = auth.replace("Bearer ", "")
        body = await request.json()
        msgs = body["messages"]
        state["calls"].append((key, msgs[-1]["content"], len(msgs)))
        state["requests"].append(msgs)
        if key.startswith("fail429"):
            return JSONResponse({"error": {"message": "rate limited", "type": "rate_limit"}}, status_code=429)
        if key.startswith("fail400"):
            return JSONResponse({"error": {"message": "bad request", "type": "invalid_request_error"}}, status_code=400)
        if key.startswith("fail500"):
            return JSONResponse({"error": {"message": "boom", "type": "server_error"}}, status_code=500)
        if state["delay"]:
            time.sleep(state["delay"])
        prompt_tokens = sum(len(m["content"].split()) + 4 for m in msgs)
        reply = f"echo({len(msgs)}): {msgs[-1]['content']}"
        completion_tokens = len(reply.split())
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens},
        }

    return app


class FakeProvider:
    def __init__(self, port: int = 18080):
        self.port = port
        self.state: dict = {}
        self.server = uvicorn.Server(
            uvicorn.Config(make_app(self.state), host="127.0.0.1", port=port, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("fake provider failed to start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


if __name__ == "__main__":  # standalone: python -m tests.fake_provider [port]
    import sys

    fp = FakeProvider(int(sys.argv[1]) if len(sys.argv) > 1 else 18080)
    fp.start()
    print(f"fake provider on {fp.base_url}", flush=True)
    fp.thread.join()
