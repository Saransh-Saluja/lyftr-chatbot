import pytest

from tests.conftest import chat


def _no_history(client, session):
    assert client.get(f"/sessions/{session}/messages").status_code == 404


def test_simulated_key1_429_fails_over_to_key2(client, provider):
    r = chat(client, "f1", "hello", {"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    m = r.json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1
    assert m["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"].startswith("echo(")          # a REAL provider answer
    assert [c[0] for c in provider.state["calls"]] == ["goodkey2"]  # key_1 never reached the provider


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_each_simulated_status_fails_over(client, status):
    r = chat(client, f"f-{status}", "hello", {"X-Simulate-Failure": f"key_1={status}"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_both_keys_simulated_fail_503_and_nothing_saved(client):
    r = chat(client, "f2", "hello", {"X-Simulate-Failure": "key_1=429,key_2=500"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    _no_history(client, "f2")


def test_wildcard_fails_everything(client):
    r = chat(client, "f3", "hello", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    _no_history(client, "f3")


def test_specific_key_overrides_wildcard(client):
    r = chat(client, "f4", "hello", {"X-Simulate-Failure": "*=429,key_2=500"})
    assert r.status_code == 503  # both still fail, but via their own statuses


def test_simulation_disabled_ignores_header(make_client):
    c = make_client(simulation=False)
    r = chat(c, "f5", "hello", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_1" and r.json()["metadata"]["fallback_attempts"] == 0


def test_invalid_simulation_header_is_422_when_enabled(client):
    for bad in ["key_1=418", "key_9=429", "garbage", "key_1="]:
        r = chat(client, "f6", "hello", {"X-Simulate-Failure": bad})
        assert r.status_code == 422, bad
    _no_history(client, "f6")


def test_real_provider_429_fails_over(make_client, provider):
    c = make_client(keys=("fail429-a", "goodkey2"), simulation=False)
    r = chat(c, "r1", "hello")
    assert r.status_code == 200
    m = r.json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1
    assert [x[0] for x in provider.state["calls"]] == ["fail429-a", "goodkey2"]  # real HTTP attempts, in order


def test_real_provider_500_fails_over(make_client):
    r = chat(make_client(keys=("fail500-a", "goodkey2"), simulation=False), "r2", "hello")
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_real_429_then_500_gives_clean_503(make_client):
    c = make_client(keys=("fail429-a", "fail500-b"), simulation=False)
    r = chat(c, "r3", "hello")
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    _no_history(c, "r3")


def test_three_keys_two_fail_counts_attempts(make_client):
    c = make_client(keys=("fail429-a", "fail500-b", "goodkey3"), simulation=False)
    m = chat(c, "r4", "hello").json()["metadata"]
    assert m["key_id"] == "key_3" and m["fallback_attempts"] == 2


def test_failed_request_does_not_pollute_existing_history(client):
    chat(client, "f7", "one")
    chat(client, "f7", "two", {"X-Simulate-Failure": "*=429"})
    msgs = client.get("/sessions/f7/messages").json()["messages"]
    assert [m["content"] for m in msgs if m["role"] == "user"] == ["one"]
