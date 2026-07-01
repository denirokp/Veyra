# AI Lab — единый чек-лист выката (go-live)

Один прогон от чистого корпуса до подключённых коллег. Детали деплоя —
`DEPLOY-FLY.md`, инструкция для коллег — `CONNECT.md`.

Приложение на Fly называется **`veyra`**, публичный URL —
`https://veyra.fly.dev/mcp`. Авторизация: **сервер открыт** (Claude.ai
поддерживает только OAuth, не статичный токен) — защита приватным URL,
`MCP_AUTH_TOKEN` **не ставим**.

---

## 0. Финальная чистка корпуса (локально)

Мусорные/раздутые доки уже удалены (`delete_docs.py`), кроме одного:

```bash
cd ~/Code/Veyra && source backend/.venv/bin/activate
# People — это Confluence MHTML-экспорт (MIME/бинарь), удаляем:
python scripts/delete_docs.py 6e4f10ad-9d5d-4688-9a27-ba8236c5c7fb

# Свежий бэкап уже чищенного корпуса — на всякий:
mkdir -p ~/Veyra-backup/$(date +%F)-clean
cp backend/data/khronika.db ~/Veyra-backup/$(date +%F)-clean/
cp -R backend/data/chroma   ~/Veyra-backup/$(date +%F)-clean/
```
> На будущих загрузках такие MHTML/бинарь-доки отсекает garbage-guard сам —
> руками чистим только те, что проиндексированы до него.

## 1. Код актуален

```bash
cd ~/Code/Veyra
git pull origin claude/mcp-ai-lab-deploy-wstvr7   # должно быть 096e6a9 или новее
```

## 2. Деплой backend

```bash
# app veyra уже создан в UI; если volume/secrets ещё нет:
fly volumes create ai_lab_data --size 1 --region ams --app veyra
fly secrets set --app veyra \
  LLM_API_KEY="dummy-not-used-on-live-path" \
  LLM_BASE_URL="https://api.anthropic.com/v1/" \
  LLM_MODEL="claude-haiku-4-5"
#   Токен и ENABLE_RERANKER НЕ ставим.

fly deploy --app veyra
```

## 3. Залить чищеный корпус на volume

```bash
cd ~/Code/Veyra
fly ssh sftp shell --app veyra <<'EOF'
cd /app/backend/data
put backend/data/khronika.db khronika.db
put -r backend/data/chroma chroma
EOF
fly machine restart $(fly status --app veyra --json | jq -r '.Machines[0].id')
```

## 4. Проверка сервера

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://veyra.fly.dev/mcp   # ждём 406 (жив, открыт)
```

## 5. Обновить skill

Скилл вырос (свежесть, охват по якорям, память, синоним-фильтр, references).
Переимпортируй `ai-lab/ai-lab-skill.zip` в Claude.ai (Settings → Skills →
удалить старый ai-lab → загрузить заново).

## 6. Коллеги подключаются

Отправь коллегам `docs/CONNECT.md` + `ai-lab/ai-lab-skill.zip`. Кратко:
Claude.ai → Settings → Connectors → Add custom → URL `https://veyra.fly.dev/mcp`,
OAuth-поля пустыми; затем импорт skill-zip.

## 7. Приёмка — прогон на живом (доказательство «как часы»)

В свежем чате Claude.ai с подключённым ai-lab прогони golden-запросы из
`ai-lab/evals/goldenset.jsonl` и сверь с `evals/rubric.md`. Минимум проверь:

- [ ] `Вызови ai-lab corpus_stats` — отдаёт число доков и `last_indexed_at`.
- [ ] «Сходится ли GMV между документами?» — пара значений с источниками и
      периодом, либо честный охват «N из M, ключевые: …».
- [ ] «Какие обещания по обучению продавцов не закрыты?» — цитаты + сроки;
      проверь, что сузилось по теме (синоним-фильтр), а не вся таблица.
- [ ] «Проверь инициативу …» — модель **дочитала `references/playbooks.md`**
      (главный риск распила) и в охвате назвала якорный документ.
- [ ] Ответ на первой строке, каждый факт с источником, охват числами+датой,
      без RAG-жаргона.

Что сломалось на живом — чиним точечно (это и есть финальная докрутка).

---

## Что дальше (после демо)

- **OAuth 2.1 + PKCE** — настоящая авторизация вместо открытого URL.
- **Reranker** — `ENABLE_RERANKER=1` на машине с бóльшим RAM (на 2 ГБ — OOM).
- **Дозагрузка доков** — `LOAD-DOCS.md` (индексируем локально → заливаем на
  volume); garbage-guard и кап xlsx уже защищают от мусора.
- **Межсессионная память** — `mark_finding` уже есть; по мере использования
  копится состояние находок (open/resolved/new-since).
