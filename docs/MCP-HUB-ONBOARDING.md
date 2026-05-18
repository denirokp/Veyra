# veyra-mcp → MCP Hub — план онбординга

Рабочий чек-лист для регистрации `veyra-mcp` в MCP Hub Avito. Закрывает
гэпы **G2** (veyra-mcp не Hub-ready) и **G3** (нет PII-анонимизации) разом:
Hub даёт OAuth через Keycloak, PII-анонимизацию (NER, fail-closed),
дистрибуцию и защиту от DOS. Онбординг = **один PR в `mcp-registry`**.

---

## Готовность `veyra-mcp` — что уже ок

- **Транспорт** `streamable-http` — Hub поддерживает Streamable HTTP «из коробки».
- **8 инструментов, все read-only** (GET-прокси к движку) → сервер для
  **Discovery Mode** (Hub-агент находит инструмент через `search_tools`).
  Write-операций нет → `pin` в Hub не нужен.
- **Docstrings инструментов** описательные, на русском — semantic-поиск
  Hub их подхватит.
- `Dockerfile` есть.

В коде `veyra-mcp/server.py`, скорее всего, **менять ничего не нужно**:
OAuth берёт на себя Hub, своей авторизации не делаем; внутренний токен
`veyra-mcp → backend` (`VEYRA_BACKEND_TOKEN`) остаётся как есть.

---

## Чек-лист онбординга

- [ ] Прочитать инструкцию `mcp-registry` — ссылка в анонсе MCP Hub
      (`docs.k.avito.ru/mcp-hub`, раздел «Подключить свой MCP-сервер»).
- [ ] **Задеплоить `veyra-mcp` на Avito PaaS** — нужен стабильный URL,
      на него ссылается запись в registry. Сейчас сервер standalone (`:8765`).
- [ ] Задеплоить backend-движок (`app.main`) — `veyra-mcp` проксирует к нему.
- [ ] Подготовить запись в `mcp-registry` (черновик ниже).
- [ ] Запросить **PII-анонимизацию** для `veyra` — корпус документов может
      содержать ПДн; Hub прогонит ответы через NER-модель.
- [ ] Открыть PR в `mcp-registry`.
- [ ] После мёржа — проверить, что `veyra` находится через `search_tools`.

---

## Черновик записи в mcp-registry

Формат — приблизительный, **сверить с актуальной схемой `mcp-registry`**:

```
имя:        veyra
описание:   Корпоративная память коммерческого блока Avito — числовые и
            логические расхождения, невыполненные обещания, пробелы по
            корпусу стратегических документов.
тип:        remote, Discovery Mode (read-only)
url:        <PaaS-URL после деплоя>
инструменты: search_corpus, find_numeric_contradictions,
            find_logic_contradictions, find_open_promises,
            list_documents, get_document, corpus_stats, health
pii:        да — включить анонимизацию (корпус может содержать ПДн)
owner:      <владелец>
```

---

## Открытые вопросы — уточнить по доке Hub

- Точный формат записи `mcp-registry` и процедура PR.
- Деплой: отдельные PaaS-сервисы под `veyra-mcp` и под backend-движок.
- Нужно ли `veyra-mcp` проверять входящий `X-Auth-Identity` от Hub —
  для read-only data-сервера, вероятно, нет, но подтвердить.

---

*Связано: `GAP-ANALYSIS-AVITO.md` (G2, G3), `ROADMAP.md` (блок «Сейчас»).*
