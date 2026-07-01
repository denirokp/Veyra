# AI Lab в Codex — настройка по шагам

Подключение MCP-сервера `ai-lab` к OpenAI **Codex CLI**. Два, что нужно:
**инструменты** (MCP-сервер по URL) и **правила** (`AGENTS.md`, т.к. у Codex
нет механизма «skills», как у Claude). ~5 минут.

**Перед началом:**
- Установлен и залогинен **Codex CLI** (`codex --version` работает).
- Локально есть репозиторий Veyra (для `AGENTS.md`) — или скачай
  `ai-lab/AGENTS.md` отдельно.
- Если api.openai.com у тебя недоступен — включи VPN.

---

## Шаг 1 — подключить инструменты (MCP-сервер)

Codex читает конфиг из `~/.codex/config.toml`. Добавь туда блок сервера:

```bash
mkdir -p ~/.codex
cat >> ~/.codex/config.toml <<'EOF'

[mcp_servers.ai-lab]
url = "https://veyra.fly.dev/mcp"
EOF
```

Что это делает: регистрирует remote streamable-HTTP MCP-сервер `ai-lab` по
URL. Сервер открытый — **токен не нужен**, поля авторизации не заполняем.

> Если позже включат `MCP_AUTH_TOKEN`, добавь в этот блок строку
> `bearer_token_env_var = "AILAB_TOKEN"` и положи токен в переменную
> окружения `AILAB_TOKEN` (Codex, в отличие от Claude.ai, умеет статичный
> Bearer).

## Шаг 2 — дать правила (`AGENTS.md`)

Это «мозги скилла» — grounding, контракт охвата, плейбуки, память находок.

**Вариант А — глобально (проще, доступно во всех сессиях Codex):**
```bash
cp ~/Code/Veyra/ai-lab/AGENTS.md ~/.codex/AGENTS.md
```
Правила в `AGENTS.md` условные («когда просят проверить инициативу /
расхождения / …»), так что обычным задачам кодинга не мешают.

**Вариант Б — только в отдельной папке (изоляция):**
```bash
mkdir -p ~/ai-lab && cp ~/Code/Veyra/ai-lab/AGENTS.md ~/ai-lab/AGENTS.md
# работать с ai-lab: cd ~/ai-lab && codex
```
Codex подхватывает `AGENTS.md` из текущего проекта — правила активны только
когда ты в этой папке.

## Шаг 3 — проверить

Запусти Codex и спроси корпус:

```bash
codex
```
В сессии:
```
вызови ai-lab corpus_stats
```
Ожидаемо: вернётся число документов (**128**) и `last_indexed_at`. Дальше
можно обычными словами: «проверь инициативу: …», «какие обещания по … не
закрыты», «нет ли расхождений по GMV».

---

## Если что-то не так

| Симптом | Что сделать |
|---|---|
| Codex не видит инструменты `ai-lab` | Проверь синтаксис `~/.codex/config.toml` (TOML, блок `[mcp_servers.ai-lab]`), перезапусти `codex`. Список подключённых MCP — командой `/mcp` внутри сессии. |
| Ошибка про `url` / сервер не поддерживается | Обнови Codex CLI — remote HTTP MCP по URL это относительно свежая возможность. |
| `401/403` от сервера | Сервер открытый, токен не нужен. Если включён `MCP_AUTH_TOKEN` — добавь `bearer_token_env_var` (см. Шаг 1). |
| Claude/Codex «рассуждает не по правилам» | Проверь, что `AGENTS.md` лежит там, откуда Codex его читает (`~/.codex/AGENTS.md` или корень текущего проекта). |

---

## Кратко (шпаргалка)

```bash
# 1. инструменты
mkdir -p ~/.codex
printf '\n[mcp_servers.ai-lab]\nurl = "https://veyra.fly.dev/mcp"\n' >> ~/.codex/config.toml

# 2. правила
cp ~/Code/Veyra/ai-lab/AGENTS.md ~/.codex/AGENTS.md

# 3. проверка
codex   # → «вызови ai-lab corpus_stats»
```
