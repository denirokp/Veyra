# veyra-mcp

MCP-сервер Veyra — корпоративная память коммерческого блока Avito как
набор инструментов для Claude / Avito AI.

## Архитектура

`veyra-mcp` — **тонкий MCP-фасад**. Он не содержит логики: каждый
инструмент проксирует запрос в HTTP-API движка (`backend/`). Движок
остаётся «толстым» сервисом — индекс корпуса, детекторы, память.
veyra-mcp отдаёт его наружу по протоколу MCP.

```
Claude / Avito AI ──MCP (streamable-http)──> veyra-mcp ──HTTP──> backend (движок)
```

## Статус: alpha

Все 8 инструментов — **чистые data-вызовы (GET к движку), ноль LLM на
стороне `veyra-mcp`.** Это и есть соответствие ТЗ, Принцип 1: на живом
пути MCP не запускает рассуждение, только подаёт предвычисленные данные
и фрагменты корпуса. `search_corpus` отдаёт сырьё retrieval (без
синтеза); рассуждение делает Claude.

Сервис **не регистрируется в production mcp-registry** до полного
прохождения retrieval-гейта (ТЗ, Принцип 1) — этап alpha, доступ только
разработчикам.

## Запуск

```bash
cd veyra-mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# движок (backend) должен быть поднят отдельно — по умолчанию :8000
VEYRA_BACKEND_URL=http://localhost:8000 python server.py
```

Переменные окружения:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `VEYRA_BACKEND_URL` | адрес движка Veyra | `http://localhost:8000` |
| `VEYRA_BACKEND_TOKEN` | bearer-токен бэкенда (если включён `API_AUTH_TOKEN`) | пусто |
| `VEYRA_MCP_HOST` / `VEYRA_MCP_PORT` | адрес самого MCP-сервера | `0.0.0.0` / `8765` |
| `VEYRA_HTTP_TIMEOUT` | таймаут запроса к бэкенду, сек | `60` |

## Инструменты

8 инструментов (соответствуют `server.py`), все — `GET` к движку:

| Инструмент | Что отдаёт | Бэкенд |
|---|---|---|
| `search_corpus(query, top_k)` | релевантные фрагменты корпуса (сырьё) | `GET /api/retrieve` |
| `find_numeric_contradictions()` | таблица числовых расхождений | `GET /api/contradictions/numeric` |
| `find_logic_contradictions()` | таблица логических расхождений | `GET /api/contradictions/logic` |
| `find_open_promises()` | незакрытые обещания | `GET /api/promises` |
| `list_documents()` | список документов корпуса | `GET /api/documents` |
| `get_document(doc_id)` | полный текст документа по id | `GET /api/documents/{id}/text` |
| `corpus_stats()` | сводка по корпусу | `GET /api/docs/stats` |
| `health()` | доступность движка | `GET /health` |

## Подключение из Claude

Как remote-MCP (streamable-http). Пример клиентской конфигурации:

```json
{
  "mcpServers": {
    "veyra": { "url": "http://<host>:8765/mcp" }
  }
}
```

## Открытые вопросы (перед production)

- Точный формат регистрации remote-MCP в Avito mcp-hub — сверить по
  `docs.k.avito.ru/mcp-hub` (путь mount, требования к health).
- Авторизация самого veyra-mcp (кто может звать инструменты) — через
  mcp-hub / Keycloak; на этапе alpha доступ только разработчикам.
- Прогон против живого MCP-клиента — сервер написан, но end-to-end с
  Claude ещё не проверялся.
