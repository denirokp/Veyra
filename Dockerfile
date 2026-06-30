# Многопроцессный контейнер для Fly.io: backend (FastAPI :8000) + MCP (:8765).
# Наружу публикуем только MCP (через fly.toml internal_port=8765).
# Данные (sqlite + chroma) — на fly volume, монтируется в /app/backend/data.

FROM python:3.11-slim AS builder

WORKDIR /build
COPY backend/requirements.txt backend-requirements.txt
COPY ai-lab-mcp/requirements.txt mcp-requirements.txt
RUN pip install --no-cache-dir --user -r backend-requirements.txt \
    && pip install --no-cache-dir --user -r mcp-requirements.txt

FROM python:3.11-slim

WORKDIR /app

# Системные либы для pdfplumber/docx + curl для healthcheck в entrypoint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /usr/local

COPY backend/app ./backend/app
COPY ai-lab-mcp/server.py ./ai-lab-mcp/server.py
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Каталоги для БД/Chroma/embed-кэша. data/ переопределяется fly volume,
# а .hf_cache лежит ВНЕ volume (в слое образа) — туда запекаем модель ниже.
RUN mkdir -p /app/backend/data/chroma /app/backend/data/docs /app/.hf_cache

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.hf_cache \
    AILAB_BACKEND_URL=http://localhost:8000 \
    AILAB_MCP_HOST=0.0.0.0 \
    AILAB_MCP_PORT=8765

# Запекаем embedding-модель в образ на этапе сборки. Иначе ~500 МБ тянулись бы
# с huggingface.co при КАЖДОМ старте машины (lifespan блокируется на загрузке
# embedder → backend не отвечает на /health, пока качает). Запечённая модель =
# детерминированный быстрый офлайн-старт. Строка модели обязана совпадать с
# settings.EMBEDDING_MODEL по умолчанию — держать в синхроне при смене модели.
ARG EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

EXPOSE 8765

CMD ["./entrypoint.sh"]
