import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, contradictions, corpus, documents, initiative, metrics, promises
from app.storage.sql_db import init_db, mark_overdue_promises, AsyncSession, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_OVERDUE_INTERVAL_HOURS = 6


async def _overdue_promises_loop() -> None:
    while True:
        await asyncio.sleep(_OVERDUE_INTERVAL_HOURS * 3600)
        try:
            async with AsyncSession(engine) as session:
                n = await mark_overdue_promises(session)
                if n:
                    logger.info("Помечено просроченных обещаний: %d", n)
        except Exception:
            logger.exception("Ошибка при проверке просроченных обещаний")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSession(engine) as session:
        n = await mark_overdue_promises(session)
        if n:
            logger.info("Помечено просроченных обещаний при старте: %d", n)
    task = asyncio.create_task(_overdue_promises_loop())
    yield
    task.cancel()


app = FastAPI(title="Хроника API", version="0.1.0", lifespan=lifespan)

from app.settings import settings as _settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.monotonic()
    response = await call_next(request)
    ms = int((time.monotonic() - t0) * 1000)
    logger.info("%s %s → %d (%dms)", request.method, request.url.path, response.status_code, ms)
    return response


app.include_router(chat.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(contradictions.router, prefix="/api")
app.include_router(promises.router, prefix="/api")
app.include_router(corpus.router, prefix="/api")
app.include_router(initiative.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
