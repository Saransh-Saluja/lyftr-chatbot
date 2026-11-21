import json
import sqlite3

import pytest

from app.database import Database
from tests.conftest import chat


def test_history_is_sent_to_the_llm(client, provider):
    chat(client, "m1", "my name is Ada")
    chat(client, "m1", "what is my name?")
    last = provider.state["requests"][-1]
    assert [m["role"] for m in last] == ["system", "user", "assistant", "user"]
    assert last[1]["content"] == "my name is Ada" and last[3]["content"] == "what is my name?"


def test_sessions_are_isolated(client, provider):
    chat(client, "iso-a", "secret alpha")
    chat(client, "iso-b", "hello beta")
    last = provider.state["requests"][-1]
    assert len(last) == 2 and "alpha" not in json.dumps(last)
    assert [m["content"] for m in client.get("/sessions/iso-b/messages").json()["messages"]][0] == "hello beta"


def test_system_prompt_persists_for_session_and_can_be_overridden(client, provider):
    chat(client, "sp", "hi", system_prompt="You are a pirate.")
    chat(client, "sp", "again")                                    # no prompt sent -> stored one is used
    assert provider.state["requests"][-1][0] == {"role": "system", "content": "You are a pirate."}
    chat(client, "sp", "third", system_prompt="You are a robot.")  # override
    assert provider.state["requests"][-1][0]["content"] == "You are a robot."
    chat(client, "other", "hi")
    assert provider.state["requests"][-1][0]["content"] == "You are a test assistant."  # default, other session


def test_system_prompt_never_stored_in_messages_or_exposed(client, tmp_path):
    chat(client, "hide", "hi", system_prompt="TOP-SECRET-PROMPT")
    body = client.get("/sessions/hide/messages").json()
    assert "TOP-SECRET-PROMPT" not in json.dumps(body)
    rows = sqlite3.connect(tmp_path / "app.db").execute("SELECT role, content FROM messages").fetchall()
    assert all(role in ("user", "assistant") for role, _ in rows)
    assert "TOP-SECRET-PROMPT" not in json.dumps(rows)


def test_history_survives_app_restart(make_client, tmp_path):
    db = tmp_path / "persist.db"
    c1 = make_client(db_path=db)
    chat(c1, "p1", "remember me")
    c1.__exit__(None, None, None)
    c2 = make_client(db_path=db)                                    # brand-new app + fresh cache
    msgs = c2.get("/sessions/p1/messages").json()["messages"]
    assert [m["content"] for m in msgs][0] == "remember me" and len(msgs) == 2
    chat(c2, "p1", "still here?")
    assert len(c2.get("/sessions/p1/messages").json()["messages"]) == 4


def test_schema_matches_contract_and_uses_wal(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 's.db'}"); db.init()
    conn = sqlite3.connect(db.path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    assert cols == ["id", "session_id", "role", "content", "metadata", "created_at"]
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    idx = [r[1] for r in conn.execute("PRAGMA index_list(messages)")]
    assert "idx_messages_session_id" in idx


def test_save_exchange_is_atomic(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 't.db'}"); db.init()
    with pytest.raises(sqlite3.IntegrityError):                     # assistant content NULL violates NOT NULL
        db.save_exchange("t", "sp", "user msg", "2026-01-01T00:00:00+00:00", None, {}, "2026-01-01T00:00:01+00:00")
    conn = sqlite3.connect(db.path)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0   # user row rolled back
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0   # session row rolled back
    assert db.get_history("t") is None


def test_upstream_400_is_clean_502_and_not_persisted(make_client):
    c = make_client(keys=("fail400-a", "goodkey2"), simulation=False)
    r = chat(c, "u1", "hi")
    assert r.status_code == 502 and r.json() == {"detail": "upstream provider rejected the request"}
    assert c.get("/sessions/u1/messages").status_code == 404


def test_api_keys_never_appear_in_responses(client):
    r = chat(client, "k1", "hi")
    assert "goodkey" not in r.text
    assert "goodkey" not in client.get("/sessions/k1/messages").text
    assert "goodkey" not in client.get("/health").text
