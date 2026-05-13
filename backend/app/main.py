import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, contradictions, docs, documents, initiative, metrics, promises
from app.storage.sql_db import init_db, mark_overdue_promises, AsyncSession, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.settings import settings
    if not settings.LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY не задан в backend/.env — задай рабочий ключ перед стартом."
        )
    await init_db()
    # Прогреваем embedding-модель на main thread — иначе первая загрузка
    # может прилететь из background_task worker'а и сломаться на meta tensor.
    from app.clients import get_embedder
    get_embedder()
    async with AsyncSession(engine) as session:
        n = await mark_overdue_promises(session)
        if n:
            logger.info("Помечено просроченных обещаний: %d", n)
    yield


app = FastAPI(title="Хроника API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(contradictions.router, prefix="/api")
app.include_router(promises.router, prefix="/api")
app.include_router(docs.router, prefix="/api")
app.include_router(initiative.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
