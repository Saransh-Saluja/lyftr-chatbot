from tests.conftest import chat

META_FIELDS = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in ("status", "keys_configured", "cache_enabled")} == {"status": "ok", "keys_configured": 2, "cache_enabled": True}
    assert body["failure_simulation"] is True


def test_health_reports_simulation_off(make_client):
    assert make_client(simulation=False).get("/health").json()["failure_simulation"] is False


def test_health_503_when_no_keys(make_client):
    r = make_client(keys=()).get("/health")
    assert r.status_code == 503 and "detail" in r.json()


def test_valid_chat_contract(client):
    r = chat(client, "s-1", "What is the capital of France?")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"session_id", "reply", "metadata"}
    assert body["session_id"] == "s-1" and body["reply"]
    m = body["metadata"]
    assert set(m) >= META_FIELDS
    assert m["resolution_source"] == "LIVE_INFERENCE"
    assert m["model"] == "openai/fake-model"
    assert m["key_id"] == "key_1" and m["fallback_attempts"] == 0
    assert isinstance(m["latency_ms"], int) and isinstance(m["input_tokens"], int) and isinstance(m["output_tokens"], int)
    assert m["input_tokens"] > 0 and m["output_tokens"] > 0


def test_422_cases_never_enter_history(client):
    cases = [
        {"message": "hi"},                                  # missing session_id
        {"session_id": "s"},                                # missing message
        {"session_id": "s", "message": ""},                 # empty
        {"session_id": "s", "message": "   \n\t "},         # whitespace only
        {"session_id": "s", "message": "x" * 4001},         # too long
        {"session_id": "", "message": "hi"},                # empty session id
        {"session_id": "s" * 129, "message": "hi"},         # session id too long
        {"session_id": "s", "message": 123},                # wrong type
    ]
    for payload in cases:
        r = client.post("/chat", json=payload)
        assert r.status_code == 422, payload
        assert "detail" in r.json()
    assert client.get("/sessions/s/messages").status_code == 404


def test_message_length_is_checked_after_trimming(client):
    assert chat(client, "s-trim", "  " + "a" * 4000 + "  ").status_code == 200
    assert chat(client, "s-trim2", "a" * 4001).status_code == 422


def test_malformed_json_is_422_json(client):
    r = client.post("/chat", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()


def test_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}


def test_unknown_route_is_json(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_history_shape_and_order(client):
    chat(client, "s-h", "first")
    chat(client, "s-h", "second")
    body = client.get("/sessions/s-h/messages").json()
    assert body["session_id"] == "s-h"
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in body["messages"] if m["role"] == "user"] == ["first", "second"]
    for m in body["messages"]:
        assert ("metadata" in m) == (m["role"] == "assistant")
        assert "system" not in m["role"]
    a = body["messages"][1]["metadata"]
    assert {"resolution_source", "input_tokens", "output_tokens"} <= set(a)
    ts = [m["created_at"] for m in body["messages"]]
    assert ts == sorted(ts)


def test_cors_allows_configured_origin_and_failure_header(client):
    r = client.options("/chat", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-simulate-failure",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    bad = client.options("/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_unhandled_error_is_json_without_stack_trace(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(client.app.state.db, "load_session", boom)
    r = chat(client, "s-x", "hi")
    assert r.status_code == 500 and r.json() == {"detail": "internal server error"}
    assert "secret" not in r.text and "Traceback" not in r.text


def test_allowed_origins_trailing_slash_is_normalised(monkeypatch):
    """'https://x.vercel.app/' must behave like 'https://x.vercel.app' (browser Origin has no slash)."""
    from app.config import Settings

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://x.vercel.app/, http://localhost:3000")
    assert Settings.from_env().allowed_origins == ("https://x.vercel.app", "http://localhost:3000")
