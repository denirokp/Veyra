# Dockerfile для backend (FastAPI + Chroma + Moonshot LLM).
# Multi-stage: builder ставит deps, runtime запускает.

FROM python:3.11-slim AS builder

WORKDIR /build

# Только pip-зависимости в этом слое — кэшируется до изменения requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage.
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для pdfplumber и docx.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные пакеты из builder.
COPY --from=builder /root/.local /usr/local

COPY app ./app

# Куда складывать БД / Chroma / документы. Эти каталоги мапятся как volume
# из docker-compose, чтобы данные переживали рестарт.
RUN mkdir -p /app/data/chroma /app/data/docs /app/data/style_anchors

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.hf_cache

# HuggingFace кэш для embedder (sentence-transformers) — volumes сохраняют
# модель между перезапусками контейнера.
RUN mkdir -p $HF_HOME

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
