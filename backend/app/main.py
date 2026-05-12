import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, contradictions, corpus, documents, initiative, metrics, promises
from app.storage.sql_db import init_db, mark_overdue_promises, AsyncSession, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
app.include_router(corpus.router, prefix="/api")
app.include_router(initiative.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
