import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fake_provider import FakeProvider


@pytest.fixture(scope="session")
def provider():
    fp = FakeProvider(port=18090)
    fp.start()
    yield fp
    fp.stop()


@pytest.fixture
def make_client(provider, tmp_path):
    """Factory: build an app + TestClient against the fake provider.

    Keys named good*/fail429*/fail500* make the FAKE PROVIDER answer for real
    with 200/429/500, so these tests exercise LiteLLM's genuine HTTP + exception
    paths (not just mocks)."""
    opened = []
    provider.state["calls"].clear()
    provider.state["requests"].clear()
    provider.state["delay"] = 0.0

    def _make(keys=("goodkey1", "goodkey2"), simulation=True, db_path=None, **overrides):
        settings = Settings(
            llm_api_keys=tuple(keys),
            llm_model="openai/fake-model",
            llm_api_base=provider.base_url,
            database_url=f"sqlite:///{db_path or tmp_path / 'app.db'}",
            allowed_origins=("http://localhost:3000",),
            enable_failure_simulation=simulation,
            default_system_prompt="You are a test assistant.",
            llm_timeout_seconds=10,
            cache_ttl_seconds=600,
            **overrides,
        )
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        client.__enter__()
        opened.append(client)
        return client

    yield _make
    for c in opened:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def chat(client, session, message, headers=None, **extra):
    return client.post("/chat", json={"session_id": session, "message": message, **extra}, headers=headers or {})
