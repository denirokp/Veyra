# Veyra

ИИ-система корпоративной памяти для коммерческого блока Avito: замечает,
**где стратегические документы спорят друг с другом** — числовые
расхождения, логические противоречия, невыполненные обещания, серые зоны.

Разрабатывается для коммерческого блока Avito (CCO Алексей Ли).
Версия ТЗ: 1.4 · май 2026

> «Хроника» — внутренний кодовик проекта; отсюда имена в коде
> (`khronika.db`, коллекции `khronika_*`, `app.title = "Хроника API"`).
> Внешнее имя продукта — **Veyra**.

---

## Что делает

- **Числовые расхождения** — одна метрика, разные значения в разных
  документах (или внутри одного документа).
- **Логические противоречия** — «здесь говорим одно, здесь другое».
- **Невыполненные обещания** — обещал / сделал, с привязкой к срокам.
- **Серые зоны** — инициативы и темы без ресурсов, владельцев, метрик.
- **Сверка инициативы** — что по теме уже изучали, что противоречит,
  чего не хватает.

Каждая находка — **с цитатой и ссылкой на документ-источник**.

**Чего Veyra НЕ делает:** не пишет документы вместо человека и не
заменяет обычный поиск по Confluence. Её ниша — **логика противоречий**.
Помощь в написании и рыночный контекст — вспомогательные возможности
(ТЗ, Возможности 5–6), не продуктовое ядро.

Подробнее — [`docs/SYSTEM.md`](docs/SYSTEM.md).

## Архитектура — три слоя

```
┌──────────────────────────────────────────────────────────────┐
│  СЛОЙ 3 — CLAUDE  (весь интеллект, на стороне клиента)        │
│  агентный цикл: ищет → читает → докапывается → сверяет        │
└───────────────────────────┬──────────────────────────────────┘
                            │ MCP (streamable-http)
┌───────────────────────────▼──────────────────────────────────┐
│  СЛОЙ 2 — veyra-mcp  (фасад данных, НОЛЬ LLM)                 │
│  8 инструментов: поиск, документы, расхождения, обещания      │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼──────────────────────────────────┐
│  СЛОЙ 1 — backend-движок                                      │
│  хранение · чанкинг · эмбеддинги · retrieval                  │
│  ChromaDB (вектора кусков) + SQLite (документы, карточки)     │
└────────────────────────────────────────────────────────────────┘
```

Доставка — не отдельный сайт, а **MCP-сервер** внутри помощника
(Claude / Avito AI). React-UI в `frontend/` — вспомогательная
админ-панель для разработки, не путь доставки. Внутреннее устройство
движка и потоки данных — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Стек

| Слой | Технология |
|------|-----------|
| LLM (dev) | OpenAI-совместимый endpoint (Moonshot Kimi / личный ключ) — переключается через `.env` |
| LLM (цель, prod) | Avito LLM Gateway, `claude-opus-4.7` (ТЗ §2) |
| Embeddings | sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (локально, ~500 МБ) |
| Vector DB | ChromaDB (persistent) |
| SQL | SQLite + SQLAlchemy async |
| Backend | FastAPI (Python 3.11+) |
| MCP-сервер | FastMCP (`veyra-mcp/`), streamable-http |
| Frontend (админ-панель) | React + TypeScript + Tailwind + Vite |
| Web search | Brave Search API (опционально, free tier 2000/мес) или Tavily |

## Структура

```
Veyra/
├── backend/                ── ДВИЖОК (Слой 1) ──
│   ├── app/
│   │   ├── agents/          # orchestrator (intent+memory), docs
│   │   ├── skills/          # extract_entities, find_*, document_brief,
│   │   │                    # deep_research, query_planner, plan_announcer,
│   │   │                    # self_check, grounding, web_research, ...
│   │   ├── rag/             # indexer, retriever (hybrid), chunker
│   │   ├── api/             # FastAPI routers
│   │   ├── models/          # Pydantic schemas
│   │   └── storage/         # ChromaDB + SQLite wrappers
│   ├── tests/ · requirements.txt · Dockerfile · .env.example
├── frontend/               ── React/Vite UI (админ-панель) ──
├── veyra-mcp/              ── MCP-СЕРВЕР (Слой 2): 8 data-инструментов ──
├── veyra-skill/            ── НАВЫК для Avito skills-hub (Слой 3) ──
├── scripts/                ── index_docs.py, run_gate.py, gate_ground_truth.json ──
├── data/                   # data/docs, data/chroma, khronika.db (gitignored)
├── docker-compose.yml
└── docs/
    ├── README.md           индекс набора документации
    ├── SYSTEM.md           полное описание системы с нуля
    ├── ARCHITECTURE.md     архитектура: слои, модель данных, потоки
    ├── SCALE-PLAN.md       план загрузки корпуса 100→300
    ├── STATUS.md           снимок статуса сессии
    ├── gate_report.md      результаты гейта детекторов
    └── TZ-Veyra.md         техническое задание (v1.4)
```

## Быстрый старт (локально, без Docker)

```bash
# 1. Backend
cd backend
cp .env.example .env       # заполни LLM_API_KEY (Moonshot или OpenAI-compatible)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Frontend (в другом терминале)
cd frontend
npm install
npm run dev
# открой http://localhost:5173
```

## Быстрый старт (Docker)

```bash
cp backend/.env.example .env
# в .env впиши LLM_API_KEY и (опционально) BRAVE_API_KEY / TAVILY_API_KEY
docker compose up -d
# открой http://localhost:8080
```

## .env обязательные параметры

```ini
# LLM (обязательно)
LLM_API_KEY=sk-...                  # ключ от Moonshot / OpenAI / любого OpenAI-compatible
LLM_BASE_URL=https://api.moonshot.ai/v1
LLM_MODEL=moonshot-v1-128k

# Web search (опционально, для research mode)
# BRAVE_API_KEY=BSA-...             # https://brave.com/search/api (free 2000/мес)
# TAVILY_API_KEY=tvly-...           # https://tavily.com (платный, лучше для research)
```

## Что работает прямо сейчас

| Фича | Состояние |
|---|---|
| Загрузка документов (pdf/docx/md/txt/html) с дедупом по SHA-256 | ✅ |
| Hybrid retrieval (vector + BM25 + RRF + hierarchy boost + dedup) | ✅ |
| Hybrid extract_entities (regex для чисел + LLM для контекста) | ✅ |
| Document briefs (markdown саммари каждого дока) | ✅ |
| Full-text mode для small corpus (≤20 доков) | ✅ |
| Brief-based mode для medium corpus | ✅ |
| Deep research с iterative refinement для 30+ доков | ✅ |
| Find contradictions (numeric, SQL fuzzy match) | ✅ |
| Find logic signals (pairwise LLM) | ✅ |
| Initiative review (RAG + contradictions + LLM synthesis) | ✅ |
| Grounding фактов (regex/fuzzy match) — защита от галлюцинаций | ✅ |
| veyra-mcp — 8 data-инструментов (alpha, не в production mcp-registry) | ✅ |
| Docker compose | ✅ |

Границы проверки и открытые риски — в [`docs/gate_report.md`](docs/gate_report.md)
и [`docs/STATUS.md`](docs/STATUS.md).

## Фазы (по ТЗ)

| Фаза | Фокус |
|------|-------|
| Фаза 1 | Гейт детекторов на 3 документах (full-text режим) |
| Фаза 1.5 | Retrieval-гейт — проверка поиска на масштабе |
| Фаза 2 | Avito LLM Gateway, индексация полного корпуса, наполнение MCP |
| Фаза 3 | Публикация skill, пилот на 3 пользователях ASD Goods |
| Фаза 4 (опц.) | Проактивность через n8n — ночной дайджест расхождений |

Полное ТЗ: [`docs/TZ-Veyra.md`](docs/TZ-Veyra.md) ·
индекс документации: [`docs/README.md`](docs/README.md)
