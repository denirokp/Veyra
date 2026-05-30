# Деплой AI Lab на Fly.io

Один контейнер: backend (FastAPI :8000) + MCP (:8765). Наружу торчит только
MCP, авторизация — Bearer token. Данные (SQLite + Chroma) на fly volume.

## Один раз: установка fly CLI

```bash
brew install flyctl
fly auth signup        # или fly auth login если аккаунт уже есть
```

## Первый деплой

```bash
cd ~/Veyra

# 1. Создаём app (Fly спросит имя — введи 'ai-lab' или подбери уникальное).
#    Не создавай DB и не деплой сразу — мы хотим сначала volume и secrets.
fly launch --no-deploy --copy-config --name ai-lab --region ams

# 2. Создаём persistent volume под данные (sqlite + chroma).
fly volumes create ai_lab_data --size 1 --region ams

# 3. Секреты. Сгенерируй сильный токен для коллег.
TOKEN=$(openssl rand -hex 32)
echo "MCP_AUTH_TOKEN=$TOKEN"   # Сохрани этот токен — отдашь коллегам.

fly secrets set MCP_AUTH_TOKEN="$TOKEN"
fly secrets set LLM_API_KEY="dummy-not-used-on-live-path"
fly secrets set LLM_BASE_URL="https://api.anthropic.com/v1/"
fly secrets set LLM_MODEL="claude-haiku-4-5"

# 4. Первый деплой — машина поднимется с пустой data/.
fly deploy
```

После деплоя — `fly status` должен показать машину `started`.

## Загрузка корпуса на volume

```bash
# Распаковываем бэкап локально.
cd ~/Veyra-backup/$(date +%Y-%m-%d)
ls -lh ai-lab-corpus-backup.tar.gz   # ~168 MB

# Заливаем на fly volume через ssh.
fly ssh sftp shell <<EOF
cd /app/backend/data
put khronika.db
put -r chroma
EOF
```

Если `sftp shell` тормозит — альтернатива через scp:

```bash
fly ssh console -C "mkdir -p /app/backend/data"
tar czf - khronika.db chroma/ | fly ssh console -C "tar xzf - -C /app/backend/data"
```

После загрузки — перезапусти машину, чтобы backend пересчитал просроченные обещания:

```bash
fly machine restart $(fly status --json | jq -r '.Machines[0].id')
```

## Проверка

```bash
APP_URL="https://ai-lab.fly.dev"

# 1. MCP endpoint без токена — 401.
curl -s -o /dev/null -w "%{http_code}\n" "$APP_URL/mcp"

# 2. С токеном — 405/406 (правильный «не голый GET, я MCP»).
curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $TOKEN" "$APP_URL/mcp"
```

## Коллеги подключаются (в Claude.ai)

Settings → Connectors → Add custom connector:

- **Name:** `ai-lab`
- **Remote MCP server URL:** `https://ai-lab.fly.dev/mcp`
- **Advanced settings → Authorization header:** `Bearer <TOKEN>`

После Add → в чате: `Вызови ai-lab corpus_stats`.

## Обновление кода

```bash
git push    # как обычно
fly deploy  # пересоберёт image и выкатит
```

Данные на volume не теряются.

## Логи и отладка

```bash
fly logs                          # стрим логов backend + MCP
fly ssh console                   # bash внутри машины
fly status                        # статус
fly machine restart <id>          # перезапуск без передеплоя
```

## Расходы

Fly.io бесплатный tier: 3 машины shared-cpu-1x по 256 MB. Мы используем
2 vCPU + 2 GB RAM — это вне free tier, ~$10–15/мес. Volume 1 GB ~$0.15/мес.
Для PoC нормально; для прод-нагрузки — пересмотреть.
