# AI Lab в Codex

Два шага: подключить MCP-сервер (инструменты) и дать правила поведения
(у Codex нет механизма «skills», как у Claude — правила идут через AGENTS.md).

## 1. Инструменты — MCP-сервер

В `~/.codex/config.toml` (глобально) или `.codex/config.toml` (в проекте):

```toml
[mcp_servers.ai-lab]
url = "https://veyra.fly.dev/mcp"
```

Codex нативно поддерживает remote streamable-HTTP MCP по URL. Сервер
открытый — токен не нужен. Если позже включат `MCP_AUTH_TOKEN` — добавь
`bearer_token_env_var = "AILAB_TOKEN"` (Codex, в отличие от Claude.ai, умеет
статичный Bearer).

Проверка: в сессии Codex попроси «вызови ai-lab corpus_stats» — должно
вернуться число документов и `last_indexed_at`.

## 2. Правила — AGENTS.md

Скопируй `ai-lab/AGENTS.md` туда, где Codex читает инструкции:
- глобально: `~/.codex/AGENTS.md`;
- или в корень рабочего проекта: `./AGENTS.md`.

Он содержит те же правила, что и `skills/SKILL.md` (grounding, контракт
охвата, плейбуки, память находок), но в одном самодостаточном файле.

## Отличия от Claude.ai

| | Claude.ai | Codex |
|---|---|---|
| Инструменты | Custom Connector (OAuth-поля пустыми) | `[mcp_servers.ai-lab] url=…` |
| Правила | импорт skill-zip | `AGENTS.md` |
| Статичный Bearer-токен | не поддерживается (только OAuth) | поддерживается (`bearer_token_env_var`) |
