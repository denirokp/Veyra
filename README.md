# Хроника / Veyra

ИИ-система корпоративной памяти — знает всё что написала команда, отвечает как коллега который всё читал.

Разрабатывается для коммерческого блока Avito (CCO Алексей Ли).  
Версия TZ: 3.0 · Май 2026

---

## Что делает

- **Полный разбор** — markdown-отчёт с разделами по нескольким документам, конкретные цифры и owner'ы
- **Поиск с цитатами** — отвечает на вопросы со ссылками на конкретные чанки документов
- **Расхождения** — детектирует числовые конфликты метрик между документами (fuzzy match + period check)
- **Реестр обещаний** — извлекает планы и дедлайны, помечает просроченные
- **Серые зоны** — что обсуждалось но не вошло в стратегию
- **Анализ инициатив** — проверка идей против корпуса с рыночным контекстом
- **Рыночный ресёрч** — multi-query Brave/Tavily поиск + синтез по конкурентам и best practices
- **Память диалога** — follow-up'ы и контекст между сообщениями

## Стек

| Слой | Технология |
|------|-----------|
| LLM (по умолчанию) | Moonshot Kimi (OpenAI-compatible API) — переключается на любой OpenAI-compatible endpoint через `.env` |
| Embeddings | sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (локально, ~500 МБ) |
| Vector DB | ChromaDB (persistent) |
| SQL | SQLite + SQLAlchemy async |
| Backend | FastAPI (Python 3.11+) |
| Frontend | React + TypeScript + Tailwind + Vite + react-markdown |
| Web search | Brave Search API (опционально, free tier 2000/мес) или Tavily |

## Архитектура

```
                     ┌────────────────────────────────────┐
                     │            React UI                │
                     │  Chat • Documents • Contradictions │
                     └────────────────┬───────────────────┘
                                      │ HTTP
                     ┌────────────────▼───────────────────┐
                     │       FastAPI Orchestrator         │
                     │  intent classifier + memory + 8    │
                     │     chat modes + auto-style        │
                     └─────┬────────────┬────────────┬────┘
                           │            │            │
              ┌────────────▼──┐  ┌──────▼─────┐  ┌──▼────────────┐
              │   docs agent   │  │ initiative │  │ deep_research │
              │ RAG + briefs   │  │  review    │  │ for 30+ docs  │
              │ + full text    │  │            │  │               │
              └────┬───────┬───┘  └────────────┘  └───────────────┘
                   │       │
        ┌──────────▼─┐  ┌──▼──────────┐
        │ retriever  │  │   skills:   │
        │ vec+BM25   │  │ • extract   │
        │ + RRF      │  │   entities  │
        └──────┬─────┘  │ • promises  │
               │        │ • logic     │
        ┌──────▼─────┐  │ • briefs    │
        │ ChromaDB + │  │ • grounding │
        │  SQLite    │  │ • web       │
        └────────────┘  └─────────────┘
```

## Структура

```
Veyra/
├── backend/
│   ├── app/
│   │   ├── agents/          # orchestrator (intent+memory), docs
│   │   ├── skills/          # extract_entities, find_*, document_brief,
│   │   │                    # deep_research, query_planner, plan_announcer,
│   │   │                    # self_check, grounding, web_research
│   │   ├── rag/             # indexer, retriever (hybrid), chunker
│   │   ├── api/             # FastAPI routers
│   │   ├── models/          # Pydantic schemas
│   │   └── storage/         # ChromaDB + SQLite wrappers
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/      # ChatInput, ModePicker, AssistantMessage, ...
│   │   ├── pages/           # ChatPage, DocumentsPage, ContradictionsPage,
│   │   │                    # LogicSignalsPage, PromisesPage, InitiativeReviewPage
│   │   ├── store/           # Zustand (с persist для истории чата)
│   │   └── api/
│   ├── Dockerfile
│   └── nginx.conf
├── data/                    # data/docs, data/chroma, khronika.db (gitignored)
├── docker-compose.yml
└── docs/
    └── TZ.md                # Техническое задание v3.0
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
| 8 chat modes с авто-выбором mode+style | ✅ |
| Память диалога (chat_messages в SQL) | ✅ |
| Grounding фактов (regex/fuzzy match) — защита от галлюцинаций | ✅ |
| Self-check + регенерация для full mode | ✅ |
| Web research через Brave/Tavily (multi-query) | ✅ |
| Markdown-рендеринг ответов в UI | ✅ |
| Collapsible секции (Источники / Расхождения / Гипотезы) | ✅ |
| Docker compose | ✅ |
| Find contradictions (numeric, SQL fuzzy match) | ✅ |
| Find logic signals (pairwise LLM) | ✅ |
| Initiative review (RAG + market + contradictions + LLM synthesis) | ✅ |

## Фазы (по ТЗ)

| Фаза | Срок | Фокус |
|------|------|-------|
| Пилот W1–W4 | май–июнь 2026 | 59 документов, 3–5 пользователей |
| Фаза 2 | Q3 2026 | 200+ документов, Market Agent, SSO |
| Фаза 3 | Q4 2026 | Кросс-опыление, fine-tuning стиля |

Полное ТЗ: [`docs/TZ.md`](docs/TZ.md)
