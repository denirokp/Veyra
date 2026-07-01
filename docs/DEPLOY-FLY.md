# Деплой AI Lab на Fly.io

Один контейнер: backend (FastAPI :8000) + MCP (:8765). Наружу торчит только
MCP. Данные (SQLite + Chroma) — на fly volume.

> **Авторизация (PoC).** Claude.ai Custom Connector поддерживает только
> **OAuth 2.1 + PKCE**, статичный Bearer-токен он прислать не может. Поэтому
> на PoC сервер **открыт** (не задаём `MCP_AUTH_TOKEN`), а защита — приватный
> URL. Настоящая авторизация — OAuth, отдельным заходом после демо.
> Bearer-middleware в коде остаётся (включается `MCP_AUTH_TOKEN`), но только
> для клиентов с кастомным заголовком (Claude Code / Avito-прокси), не Claude.ai.

## Один раз: установка fly CLI

```bash
brew install flyctl
fly auth signup        # или fly auth login если аккаунт уже есть
```

## Первый деплой

```bash
cd ~/Code/Veyra

# 1. Создаём app (имя должно совпасть с fly.toml → app = "veyra").
fly launch --no-deploy --copy-config --name veyra --region ams

# 2. Persistent volume под данные (sqlite + chroma).
fly volumes create ai_lab_data --size 1 --region ams --app veyra

# 3. Секреты. Токен НЕ ставим (см. про авторизацию выше). LLM_* нужны только
#    чтобы backend прошёл startup-гейт — живой путь MCP их не зовёт (эмбеддинги
#    локальные). ENABLE_RERANKER не задаём: на 2GB вторая модель = риск OOM.
fly secrets set --app veyra \
  LLM_API_KEY="dummy-not-used-on-live-path" \
  LLM_BASE_URL="https://api.anthropic.com/v1/" \
  LLM_MODEL="claude-haiku-4-5"

# 4. Первый деплой — образ соберётся с запечённой embed-моделью.
fly deploy --app veyra
```

После деплоя — `fly status --app veyra` должен показать машину `started`.

## Загрузка корпуса на volume

> ⚠️ Заливать **тарболом через sftp**, а НЕ потоком через `fly ssh console`
> (pty корёжит бинарь → `khronika.db` приезжает битый, backend не стартует).

```bash
cd ~/Code/Veyra/backend/data
tar czf /tmp/corpus.tgz khronika.db chroma      # тарбол локально

fly ssh console --app veyra -C "sh -lc 'rm -rf /app/backend/data/khronika.db /app/backend/data/chroma /app/backend/data/corpus.tgz'"

fly ssh sftp shell --app veyra <<'EOF'
put /tmp/corpus.tgz /app/backend/data/corpus.tgz
EOF

# Сверить размер (байт-в-байт с локальным), распаковать НА машине.
fly ssh console --app veyra -C "ls -l /app/backend/data/corpus.tgz"
fly ssh console --app veyra -C "sh -lc 'cd /app/backend/data && tar xzf corpus.tgz && rm corpus.tgz'"

# Рестарт — backend пересчитает просроченные обещания и подхватит корпус.
fly machine restart $(fly status --app veyra --json | jq -r '.Machines[0].id') --app veyra
```

## Проверка

```bash
# Сервер открыт (PoC): без токена MCP отвечает 406 (жив, «я не голый GET»).
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://veyra.fly.dev/mcp   # ждём 406
```

## Коллеги подключаются (в Claude.ai)

Полная инструкция для коллег — `docs/CONNECT-SIMPLE.md`. Коротко:

Settings → Connectors → Add custom connector:

- **Name:** `ai-lab`
- **Remote MCP server URL:** `https://veyra.fly.dev/mcp`
- **Advanced → OAuth Client ID / Secret:** оставить **пустыми** (сервер открыт)

Плюс импортировать skill `ai-lab/ai-lab-skill.zip`. Проверка в чате:
`Вызови ai-lab corpus_stats`.

## Обновление кода

```bash
git push          # как обычно
fly deploy --app veyra
```

Данные на volume не теряются.

## Логи и отладка

```bash
fly logs --app veyra
fly ssh console --app veyra
fly status --app veyra
fly machine restart <id> --app veyra
```

## Расходы

2 vCPU + 2 GB RAM — вне free tier, ~$10–15/мес. Volume 1 GB ~$0.15/мес. Для
PoC нормально; для прод-нагрузки (и reranker) — брать машину с бóльшим RAM.
