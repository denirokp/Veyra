# CLAUDE.md — навигация по репозиторию

Точка входа для агента и для человека. Читается каждую сессию.
Продукт — **Хроника**; `Veyra` — кодовое имя движка.

## Что это

Система институциональной памяти над корпусом стратегических документов:
находит противоречия (числовые и логические), ведёт реестр обещаний,
выявляет серые зоны, сбивает новые инициативы с корпусом.
Позиционирование и ров — `docs/positioning.md` (читать первым).

## Архитектура — два слоя

- **Слой A — корпусный движок.** Ingestion → чанкинг → эмбеддинги →
  Chroma + гибридный retrieval + БД находок. Кастомный оправданно,
  масштабируется на 200+ доков. Это ров.
- **Слой B — оркестрация.** Сейчас: `route_request()` → enum-режим →
  single-shot RAG. Цель рефактора — tool-use loop (скиллы как tools).
  Это table stakes.

Не смешивать. Усилие — в слой A и качество находок.

## Карта репозитория

```
backend/app/
  main.py              FastAPI entrypoint
  settings.py          конфиг из .env
  clients.py           LLM-клиент (Claude через Avito AI proxy)
  agents/
    orchestrator.py    route_request() + run() — роутинг запроса
    corpus.py          RAG + LLM-генерация, FACT/HYPOTHESIS JSON
  rag/
    indexer.py         парсинг (pdf/docx/md/txt/html) + индексация
    chunker.py         токен-aware чанкинг
    retriever.py       гибрид: vector + BM25 + RRF + hierarchy boost
  skills/              9 скиллов: find_contradictions, find_logic_signals,
                       track_promises, find_gaps, suggest_missing_metrics,
                       market_agent, initiative_review, extract_entities,
                       build_graph. Запускаются при индексации (фон)
                       и через API — НЕ через чат-оркестратор.
  api/                 chat, contradictions, corpus, documents,
                       initiative, metrics, promises
  storage/             sql_db.py (SQLite), vector_db.py (Chroma)
  models/schemas.py    Pydantic-схемы
backend/prompts/       промпты-как-файлы (router.txt, corpus_system.txt, …)
frontend/src/          React + TS + Vite + Tailwind, Zustand store
  pages/               Chat, Corpus, Contradictions, LogicSignals,
                       Promises, InitiativeReview
scripts/               index_corpus.py (первичная индексация), run_eval.py
tests/                 eval_set.yaml, test_eval_structure.py
docs/                  positioning.md, eval-seed.md, decisions/ (ADR)
data/                  corpus/ (доки, не в git), chroma/, khronika.db
```

## Запуск

```bash
# Backend
cd backend && cp .env.example .env   # заполнить ключи
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

python scripts/index_corpus.py       # первичная индексация корпуса
python scripts/run_eval.py           # прогон eval

# Frontend
cd frontend && npm install && npm run dev
```

## Конвенции и инварианты

- **LLM** — Claude через Avito AI proxy (`ANTHROPIC_BASE_URL`).
  **Эмбеддинги** — `text-embedding-3-large` через `OPENAI_BASE_URL`
  (тоже Avito proxy — данные не уходят наружу напрямую).
- **Промпты — в файлах** `backend/prompts/`, не в коде. Править там.
- **Вывод корпус-агента** — структурированный JSON: `answer`, `facts`,
  `hypotheses`, `warnings`, `requires_verification`. Каждый факт
  ссылается на источник по 1-based номеру (`source_id`).
- **Иерархия документов** — `hierarchy_level` L1–L6; retriever усиливает
  L1/L2, штрафует L5/L6. Неформальные входы → низкий уровень.
- **Статусы документов** — actual / draft / archived / superseded /
  unknown; superseded исключаются из вектора.
- **Находки** имеют жизненный цикл: open → reviewed → resolved/dismissed.
- Загруженные файлы оборачиваются и проверяются на prompt-injection
  (`corpus.py`).

## Текущий фокус

Дорожная карта и приоритеты — в `docs/positioning.md` (раздел «что
следует»). Кратко: ров = качество детекции + eval + жизненный цикл
находок; table stakes = tool-use loop + MCP, без переинвестиций.

## Известные расхождения

- `docs/TZ.md` упоминается в README, но отсутствует в репозитории.
- Чат-оркестратор — single-shot, не agentic loop (цель рефактора).
- При извлечении из .docx таблицы схлопываются — нужна table-aware
  разметка для корректной привязки «метрика → значение».
