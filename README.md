# Хроника

ИИ-система корпоративной памяти — знает всё что написала команда, отвечает как коллега который всё читал.

Разрабатывается для коммерческого блока Avito (CCO Алексей Ли).  
Версия TZ: 3.0 · Май 2026

---

## Что делает

- Отвечает на вопросы по корпусу документов с ссылками на источники
- Находит числовые расхождения между документами
- Ведёт реестр обещаний и планов
- Выявляет серые зоны — темы изученные, но не вошедшие в стратегию
- Пишет документы в стиле команды на основе корпуса

## Стек

| Слой | Технология |
|------|-----------|
| LLM | Claude Sonnet 4 (Avito AI proxy) |
| Embeddings | text-embedding-3-large |
| Vector DB | ChromaDB → Qdrant при масштабе |
| Graph + SQL | SQLite + NetworkX |
| Backend | FastAPI (Python 3.11+) |
| Frontend | React + TypeScript + Tailwind |

## Структура

```
Хроника/
├── backend/
│   ├── app/
│   │   ├── agents/          # Orchestrator, CorpusAgent
│   │   ├── skills/          # extract_entities, find_contradictions, ...
│   │   ├── rag/             # indexer, retriever, chunker
│   │   ├── api/             # FastAPI routers
│   │   ├── models/          # Pydantic schemas
│   │   └── storage/         # ChromaDB + SQLite wrappers
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/           # Chat, Corpus, Contradictions, Promises, Write
│       ├── store/           # Zustand
│       └── api/
├── data/
│   ├── corpus/              # загруженные документы (не в git)
│   └── style_anchors/       # эталоны стиля (не в git)
├── docs/
│   └── TZ.md                # Техническое задание v3.0
└── scripts/
    └── index_corpus.py      # первичная индексация
```

## Быстрый старт

```bash
# Backend
cd backend
cp .env.example .env       # заполни ключи
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Первичная индексация корпуса
python scripts/index_corpus.py

# Frontend
cd frontend
npm install
npm run dev
```

## Фазы

| Фаза | Срок | Фокус |
|------|------|-------|
| Пилот W1–W4 | май–июнь 2026 | 59 документов, 3–5 пользователей |
| Фаза 2 | Q3 2026 | 200+ документов, Market Agent, SSO |
| Фаза 3 | Q4 2026 | Кросс-опыление, fine-tuning стиля |

Полное ТЗ: [`docs/TZ.md`](docs/TZ.md)
