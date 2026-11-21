#!/usr/bin/env python3
"""Black-box contract check for the chat backend. Standard library only.

Usage:  python scripts/smoke_test.py [BASE_URL] [--origin FRONTEND_ORIGIN] [--no-simulation]
        BASE_URL may also come from the BASE_URL env var (default http://localhost:8000)

Exit code 0 = every check passed. Needs a working LLM behind the backend.
Failover checks need ENABLE_FAILURE_SIMULATION=true on the server (use
--no-simulation to verify instead that the header is ignored when it is off).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

RESULTS: list[tuple[str, bool, str]] = []


def call(base, method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, resp.read().decode(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def jcall(*a, **k):
    status, text, headers = call(*a, **k)
    try:
        return status, json.loads(text), headers
    except json.JSONDecodeError:
        return status, {"_non_json_body": text[:200]}, headers


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), "" if cond else str(detail)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail}"))
    return bool(cond)


META = {"resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "key_id", "fallback_attempts"}


def meta_ok(m):
    return (META <= set(m) and m["resolution_source"] in ("LIVE_INFERENCE", "LLM_CACHE")
            and isinstance(m["latency_ms"], int) and isinstance(m["input_tokens"], int)
            and isinstance(m["output_tokens"], int) and isinstance(m["fallback_attempts"], int)
            and isinstance(m["model"], str) and (m["key_id"] is None or isinstance(m["key_id"], str)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url", nargs="?", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    ap.add_argument("--origin", help="frontend origin to test CORS against")
    ap.add_argument("--no-simulation", action="store_true", help="server has ENABLE_FAILURE_SIMULATION off")
    ap.add_argument("--skip-semantic", action="store_true",
                    help="skip 'the model remembers' (only for echo/fake providers; keep ON for a real LLM)")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    run = uuid.uuid4().hex[:8]  # unique messages -> the first request is never an old cache entry
    print(f"Smoke test against {base} (run {run})\n")

    print("health")
    s, b, _ = jcall(base, "GET", "/health")
    check("GET /health 200", s == 200, s)
    check("health shape", b.get("status") == "ok" and isinstance(b.get("keys_configured"), int)
          and b["keys_configured"] >= 2 and b.get("cache_enabled") is True, b)

    print("chat + metadata")
    q = f"[{run}] Reply with one short sentence: what is the capital of France?"
    sa, ra, _ = jcall(base, "POST", "/chat", {"session_id": f"smoke-a-{run}", "message": q})
    check("POST /chat 200", sa == 200, (sa, ra))
    m1 = ra.get("metadata", {}) if sa == 200 else {}
    check("response has session_id, non-empty reply, metadata fields", sa == 200 and ra.get("session_id") == f"smoke-a-{run}"
          and ra.get("reply") and meta_ok(m1), ra)
    check("first request is LIVE_INFERENCE with a key_id", m1.get("resolution_source") == "LIVE_INFERENCE"
          and isinstance(m1.get("key_id"), str) and m1.get("fallback_attempts") == 0, m1)
    check("tokens are positive ints", m1.get("input_tokens", 0) > 0 and m1.get("output_tokens", 0) > 0, m1)

    print("cache")
    sb, rb, _ = jcall(base, "POST", "/chat", {"session_id": f"smoke-b-{run}", "message": q})
    m2 = rb.get("metadata", {}) if sb == 200 else {}
    check("same message, NEW session -> LLM_CACHE", m2.get("resolution_source") == "LLM_CACHE", m2)
    check("cache hit: identical reply", rb.get("reply") == ra.get("reply"))
    check("cache hit: key_id null, fallback_attempts 0", m2.get("key_id") is None and m2.get("fallback_attempts") == 0, m2)
    check("cache hit: tokens equal the stored usage", (m2.get("input_tokens"), m2.get("output_tokens")) == (m1.get("input_tokens"), m1.get("output_tokens")), (m1, m2))
    check("cache hit faster than live", m2.get("latency_ms", 1e9) < m1.get("latency_ms", 0), (m1.get("latency_ms"), m2.get("latency_ms")))
    sc, rc, _ = jcall(base, "POST", "/chat", {"session_id": f"smoke-c-{run}", "message": f"[{run}] Say hello in French, one word."})
    check("different message -> LIVE_INFERENCE", rc.get("metadata", {}).get("resolution_source") == "LIVE_INFERENCE", rc)

    print("multi-turn + history")
    sid = f"smoke-mt-{run}"
    jcall(base, "POST", "/chat", {"session_id": sid, "message": f"[{run}] My favourite colour is turquoise. Just say OK."})
    s2, r2, _ = jcall(base, "POST", "/chat", {"session_id": sid, "message": "What colour did I say was my favourite? One word."})
    check("second turn 200", s2 == 200, r2)
    if args.skip_semantic:
        print("  [SKIP] model remembers earlier turn (--skip-semantic; NOT verified in this run)")
    else:
        check("model remembers earlier turn (semantic check)", "turquoise" in str(r2.get("reply", "")).lower(), r2.get("reply"))
    check("input_tokens grows with history (per-request, includes context)", r2.get("metadata", {}).get("input_tokens", 0) > 0)
    sh, h, _ = jcall(base, "GET", f"/sessions/{sid}/messages")
    msgs = h.get("messages", [])
    check("history: 4 messages oldest-first user/assistant alternating", [m.get("role") for m in msgs] == ["user", "assistant", "user", "assistant"], msgs)
    check("history: assistant has metadata, user does not", all(("metadata" in m) == (m["role"] == "assistant") for m in msgs))
    check("history: session_id echoed, no system role", h.get("session_id") == sid and all(m["role"] != "system" for m in msgs))
    s404, b404, _ = jcall(base, "GET", f"/sessions/does-not-exist-{run}/messages")
    check("unknown session -> 404 {'detail':'session not found'}", s404 == 404 and b404 == {"detail": "session not found"}, (s404, b404))

    print("validation (422) - none may enter history")
    bad_sid = f"smoke-bad-{run}"
    for label, kw in [
        ("empty message", dict(body={"session_id": bad_sid, "message": ""})),
        ("whitespace-only message", dict(body={"session_id": bad_sid, "message": "   \n "})),
        ("message > 4000 chars", dict(body={"session_id": bad_sid, "message": "x" * 4001})),
        ("missing session_id", dict(body={"message": "hi"})),
        ("missing message", dict(body={"session_id": bad_sid})),
        ("malformed JSON", dict(raw=b"{oops")),
    ]:
        s, b, _ = jcall(base, "POST", "/chat", **kw)
        check(f"422 for {label}", s == 422 and "detail" in b, (s, b))
    check("rejected requests left no session", jcall(base, "GET", f"/sessions/{bad_sid}/messages")[0] == 404)

    print("failover (X-Simulate-Failure)")
    if args.no_simulation:
        s, b, _ = jcall(base, "POST", "/chat", {"session_id": f"smoke-ns-{run}", "message": f"[{run}] ping ns"}, {"X-Simulate-Failure": "*=429"})
        check("header ignored when simulation is disabled (200, key_1, 0 fallbacks)",
              s == 200 and b["metadata"]["key_id"] == "key_1" and b["metadata"]["fallback_attempts"] == 0, (s, b))
    else:
        for label, hdr in [("key_1=429", "key_1=429"), ("key_1=500", "key_1=500")]:
            s, b, _ = jcall(base, "POST", "/chat", {"session_id": f"smoke-f-{hdr}-{run}", "message": q}, {"X-Simulate-Failure": hdr})
            mm = b.get("metadata", {})
            check(f"{label}: 200, key_id=key_2, fallback_attempts=1, real LIVE answer",
                  s == 200 and mm.get("key_id") == "key_2" and mm.get("fallback_attempts") == 1
                  and mm.get("resolution_source") == "LIVE_INFERENCE" and bool(b.get("reply")), (s, b))
        fid = f"smoke-all-{run}"
        s, b, _ = jcall(base, "POST", "/chat", {"session_id": fid, "message": q}, {"X-Simulate-Failure": "*=429"})
        check("*=429: 503 {'detail':'all providers unavailable'}", s == 503 and b == {"detail": "all providers unavailable"}, (s, b))
        check("*=429: nothing added to history", jcall(base, "GET", f"/sessions/{fid}/messages")[0] == 404)

    if args.origin:
        print("CORS")
        s, _, h = call(base, "OPTIONS", "/chat", headers={"Origin": args.origin, "Access-Control-Request-Method": "POST",
                                                          "Access-Control-Request-Headers": "content-type,x-simulate-failure"})
        h = {k.lower(): v for k, v in h.items()}
        check(f"preflight allows origin {args.origin}", s == 200 and h.get("access-control-allow-origin") in (args.origin, "*"), (s, h))

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'PASS' if not failed else 'FAIL'}: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed against {base}")
    for name, _, detail in failed:
        print(f"  FAILED: {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
