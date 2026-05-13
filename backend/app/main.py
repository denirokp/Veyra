import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

from app.settings import settings as _settings
_cors_origins = [o.strip() for o in _settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    # Только нужные методы. Без OPTIONS не пройдёт preflight.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    # Только нужные хедеры — Authorization для bearer, Content-Type для JSON/multipart.
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def _auth_and_body_limit(request: Request, call_next):
    """Опциональный bearer-токен + защита от слишком больших bodies.

    Health-check и preflight остаются открытыми. Если API_AUTH_TOKEN не
    задан — все эндпоинты доступны (local dev). Если задан — non-health
    требуют корректный Bearer.
    """
    path = request.url.path
    method = request.method

    # Тело — отбрасываем превышение раньше любых auth/CPU работ.
    cl = request.headers.get("content-length")
    if cl and cl.isdigit():
        if int(cl) > _settings.MAX_REQUEST_BODY_MB * 1024 * 1024:
            return JSONResponse(
                {"detail": f"Request body too large (max {_settings.MAX_REQUEST_BODY_MB} MB)"},
                status_code=413,
            )

    # /health и preflight — без auth
    if path == "/health" or method == "OPTIONS":
        return await call_next(request)

    if _settings.API_AUTH_TOKEN:
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {_settings.API_AUTH_TOKEN}"
        if auth != expected:
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


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
