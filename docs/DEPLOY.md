# Deploy — бриф для разработчика

Что нужно вывести с личного компа на Avito PaaS, чтобы коллеги могли
тестить veyra-mcp не через туннель. Это описание топологии и требований —
PaaS-манифесты (atlas / helmgen) разработчик пишет под нашу платформу сам.

## Что деплоим — 2 сервиса

| Сервис | Порт | Dockerfile | Роль |
|---|---|---|---|
| **backend** | 8000 | `backend/Dockerfile` | движок: RAG + детекторы + корпус. Внутренний. |
| **veyra-mcp** | 8765 | `veyra-mcp/Dockerfile` | тонкий MCP-фасад над backend. **Внешний** (его зовёт Claude коллег). |

`frontend/` (React-панель) — для теста коллегами **не нужен**, можно не деплоить.

`veyra-mcp` — это streamable-http MCP, путь `/mcp`. Коллеги подключают
`https://<внешний-адрес>/mcp` в `avito ai claude` / claude.ai как custom MCP.

## Сеть

- **veyra-mcp** — внешний роут (внутри `*.k.avito.ru`), доступен коллегам.
- **backend** — только внутренний; `veyra-mcp` ходит в него по
  `VEYRA_BACKEND_URL=http://backend:8000`.

## Env

**backend** (полный список — `backend/.env.example`):
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` — указать на **Avito AI proxy**
  (OpenAI-совместимый), а не на личный ключ Moonshot.
- `DATABASE_URL=sqlite+aiosqlite:////app/data/khronika.db`
- `CHROMA_PERSIST_DIR=/app/data/chroma`, `DOCS_DIR=/app/data/docs`
- `API_AUTH_TOKEN=<случайный токен>` — закрыть API в проде.
- `ENABLE_LEGACY_CHAT=0` — без React-панели нужен только слой данных.
- `CORS_ORIGINS` — не критично без фронта.

**veyra-mcp**:
- `VEYRA_BACKEND_URL=http://backend:8000`
- `VEYRA_BACKEND_TOKEN=<тот же API_AUTH_TOKEN>` — иначе backend ответит 401.
- `VEYRA_MCP_HOST=0.0.0.0`, `VEYRA_MCP_PORT=8765`

Токены — через секреты PaaS, не в манифест.

## Данные корпуса — главное

backend бесполезен без проиндексированного корпуса. Нужен **персистентный
том** на `/app/data` со структурой: `khronika.db`, `chroma/`, `docs/`.

Два пути наполнить:
1. **Засеять существующим индексом** — скопировать `data/` с рабочей машины
   в том (быстро, но текущий 28-док прогон частично дырявый).
2. **Переиндексировать в проде** — положить исходники в `docs/`, выполнить
   `python scripts/index_docs.py` (нужен рабочий `LLM_*` = Avito proxy).
   Чистый вариант, но стоит LLM-вызовов.

Рекомендация: после переезда на Avito proxy — путь 2 (чистый реиндекс).

## Embedding-модель

Первый старт backend качает `sentence-transformers/...` (~500 МБ) с
huggingface. Варианты: разрешить egress на huggingface на первом старте,
либо **забандлить модель в образ / в том** и выставить
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`, чтобы старт не зависел от сети.

## Чек-лист для PaaS

- [ ] 2 сервиса (backend, veyra-mcp) из их Dockerfile
- [ ] backend: персистентный том `/app/data` + засев/реиндекс корпуса
- [ ] секреты: `LLM_API_KEY`, `API_AUTH_TOKEN`
- [ ] `LLM_BASE_URL` → Avito AI proxy
- [ ] внешний роут на veyra-mcp `/mcp`; backend — внутренний
- [ ] embedding-модель: egress или бандл + offline-флаги

## Дальше — mcp-registry

Когда сервис живёт на PaaS — PR в `mcp-registry`, чтобы veyra появился у
коллег в `avito ai claude` без ручного добавления URL (с OAuth).
