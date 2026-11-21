"""Caching tests run through the REAL litellm.acompletion + REAL litellm cache,
talking HTTP to the fake provider. `provider.state['calls']` is the ground truth
for 'did a live call actually happen?', so a silent cache miss cannot hide."""
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import chat

Q = "What is the capital of France?"


def test_cross_session_cache_hit_is_immediate_and_identical(client, provider):
    first = chat(client, "A", Q).json()
    second = chat(client, "B", Q).json()          # NEW session, sent immediately (no sleep)
    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert second["metadata"]["resolution_source"] == "LLM_CACHE"
    assert second["reply"] == first["reply"]
    assert second["metadata"]["key_id"] is None
    assert second["metadata"]["fallback_attempts"] == 0
    assert second["metadata"]["input_tokens"] == first["metadata"]["input_tokens"]
    assert second["metadata"]["output_tokens"] == first["metadata"]["output_tokens"]
    assert len(provider.state["calls"]) == 1       # provider really was hit only once


def test_different_message_is_never_served_from_cache(client, provider):
    chat(client, "A", Q)
    r = chat(client, "B", "What is the capital of Spain?").json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert "Spain" in r["reply"] and "France" not in r["reply"]
    assert len(provider.state["calls"]) == 2


def test_different_system_prompt_is_a_different_cache_entry(client, provider):
    chat(client, "A", Q, system_prompt="Answer like a pirate.")
    r = chat(client, "B", Q).json()               # default system prompt
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    r2 = chat(client, "C", Q, system_prompt="Answer like a pirate.").json()
    assert r2["metadata"]["resolution_source"] == "LLM_CACHE"


def test_cache_identity_covers_full_history(client, provider):
    chat(client, "A", "m1"); chat(client, "A", "m2")
    same = chat(client, "B", "m1"); same2 = chat(client, "B", "m2").json()
    assert same2["metadata"]["resolution_source"] == "LLM_CACHE"       # identical full list
    chat(client, "C", "different-first")
    diverged = chat(client, "C", "m2").json()
    assert diverged["metadata"]["resolution_source"] == "LIVE_INFERENCE"  # same last msg, different history


def test_cache_hit_does_not_depend_on_which_key_answered(make_client, provider):
    c = make_client(keys=("fail429-a", "goodkey2"), simulation=False)
    first = chat(c, "A", Q).json()                # answered by key_2 after a real 429
    assert first["metadata"]["key_id"] == "key_2"
    second = chat(c, "B", Q).json()
    assert second["metadata"]["resolution_source"] == "LLM_CACHE" and second["metadata"]["key_id"] is None


def test_cache_hit_is_faster_than_live(client, provider):
    provider.state["delay"] = 0.4                 # controlled: live call costs >= 400 ms
    live = chat(client, "A", Q).json()["metadata"]
    hit = chat(client, "B", Q).json()["metadata"]
    assert live["latency_ms"] >= 400
    assert hit["latency_ms"] < live["latency_ms"] / 2


def test_simulated_request_bypasses_cache_read(client, provider):
    chat(client, "A", Q)                          # warm the cache (key_1 live)
    r = chat(client, "B", Q, {"X-Simulate-Failure": "key_1=429"}).json()["metadata"]
    assert r["resolution_source"] == "LIVE_INFERENCE" and r["key_id"] == "key_2" and r["fallback_attempts"] == 1


def test_simulated_request_does_not_write_cache(client, provider):
    chat(client, "A", "fresh question", {"X-Simulate-Failure": "key_1=500"})
    r = chat(client, "B", "fresh question").json()["metadata"]
    assert r["resolution_source"] == "LIVE_INFERENCE"   # first NORMAL request must be live


def test_concurrent_identical_requests_cost_one_provider_call(client, provider):
    provider.state["delay"] = 0.3
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda i: chat(client, f"c{i}", "concurrent q").json(), range(3)))
    sources = sorted(r["metadata"]["resolution_source"] for r in results)
    assert sources == ["LIVE_INFERENCE", "LLM_CACHE", "LLM_CACHE"]
    assert len(provider.state["calls"]) == 1


def test_tokens_are_per_request_not_cumulative(client):
    a = chat(client, "A", "same length one").json()["metadata"]
    b = chat(client, "B", "same length two").json()["metadata"]
    assert a["input_tokens"] == b["input_tokens"]                 # equal-length first messages
    a2 = chat(client, "A", "follow up").json()["metadata"]
    assert a2["input_tokens"] > a["input_tokens"]                 # grows with history (context)...
    assert a2["output_tokens"] <= a2["input_tokens"]              # ...but output is only the new reply
    assert chat(client, "D", "same length one").json()["metadata"]["input_tokens"] == a["input_tokens"]


def test_write_through_makes_back_to_back_repeat_a_hit(provider):
    """Pins the explicit cache write-through. LiteLLM 1.110.2 writes the cache in a
    background task (~95 ms lag); two awaits with no event-loop yield in between
    would otherwise miss. (Found via a direct probe; HTTP-level tests alone do not
    reproduce it because the DB await gives the background task time to run.)"""
    import asyncio

    from app.config import Settings
    from app.services.llm import LLMService

    settings = Settings(("goodkey1", "goodkey2"), "openai/fake-model", provider.base_url, "sqlite:///x.db",
                        (), False, "sys", 10, 600)
    svc = LLMService(settings)
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "back to back"}]

    async def go():
        return await svc.complete(msgs), await svc.complete(msgs)

    a, b = asyncio.run(go())
    assert (a.source, b.source) == ("LIVE_INFERENCE", "LLM_CACHE")
    assert b.reply == a.reply and (b.input_tokens, b.output_tokens) == (a.input_tokens, a.output_tokens)
