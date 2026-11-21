import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.database import Database
from app.routers import chat, health, sessions
from app.services.llm import LLMService
from app.services.locks import KeyedLock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        db.init()  # schema is created automatically on startup
        app.state.settings = settings
        app.state.db = db
        app.state.llm = LLMService(settings)
        app.state.session_locks = KeyedLock()
        if len(settings.llm_api_keys) < 2:
            log.warning("only %d API key(s) configured; failover needs at least 2", len(settings.llm_api_keys))
        log.info("started: model=%s keys=%d simulation=%s", settings.llm_model,
                 len(settings.llm_api_keys), settings.enable_failure_simulation)
        yield

    app = FastAPI(title="Lyftr Chat Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],  # includes Content-Type and X-Simulate-Failure
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    return app


app = create_app()
