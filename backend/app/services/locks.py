import asyncio
from contextlib import asynccontextmanager


class KeyedLock:
    """One asyncio.Lock per string key, freed when nobody uses it (no memory leak)."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._users: dict[str, int] = {}

    @asynccontextmanager
    async def hold(self, key: str):
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._users[key] -= 1
            if self._users[key] == 0:
                del self._users[key]
                del self._locks[key]
