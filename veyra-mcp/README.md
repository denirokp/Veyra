# veyra-mcp

MCP-сервер Veyra — детекторы расхождений, противоречий и невыполненных
обещаний в стратегических документах коммерческого блока Avito.

## Статус: Фаза 1, Трек B — skeleton

Все инструменты возвращают заглушки (`{"status": "not_implemented", "stub": true}`).
Реальная логика (retrieval + детекторы) заливается в Фазе 2, Трек E —
**только после прохождения гейта детекторов** (Принцип 1 ТЗ v1.3).

`/health` — единственный неглушёный эндпоинт.

## Запуск локально

```bash
cd veyra-mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Проверка:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/tools/check_initiative \
  -H 'Content-Type: application/json' -d '{"text":"пример инициативы"}'
```

Тесты: `pytest tests/ -q`

## Эндпоинты (контракт зафиксирован, тела — заглушки)

| Эндпоинт | Вход | Назначение (Трек E) |
|---|---|---|
| `GET /health` | — | health-check (реальный) |
| `POST /tools/check_initiative` | `{text}` | сверка инициативы с корпусом → расхождения |
| `POST /tools/find_contradictions` | `{doc_id}` | расхождения для документа из корпуса |
| `POST /tools/search_corpus` | `{query, top_k}` | retrieval по корпусу |
| `POST /tools/get_document` | `{doc_id}` | полный текст документа для цитат |

## Авторизация

`app/auth.py` — пока заглушка. Dev-режим: если задан `VEYRA_MCP_DEV_TOKEN`,
требуется заголовок `Authorization: Bearer <token>`; иначе сервис открыт
(локальная разработка). Реальный Keycloak Avito подключается при выходе
на PaaS — меняется только тело `require_auth`.

## Открытый вопрос — транспорт MCP

Сейчас инструменты отдаются как обычные REST-эндпоинты — этого достаточно
для smoke-теста инфраструктуры (PaaS, Keycloak, mcp-registry). Требует ли
Avito MCP Hub именно MCP-протокол (streamable HTTP / JSON-RPC) для remote-
серверов — **уточнить по `docs.k.avito.ru/mcp-hub`**. Логика инструментов
вынесена в `app/tools.py` транспортно-независимо: при необходимости поверх
неё добавляется MCP-протокольный слой без переписывания самих инструментов.

## Чего НЕ делать (Принцип 1 ТЗ)

- Не заливать реальную логику детекторов до прохождения гейта.
- Не вызывать LLM и не подключать индекс корпуса из эндпоинтов на Фазе 1.
- Не мерджить в production mcp-registry — только draft PR с пометкой `[ALPHA]`.
