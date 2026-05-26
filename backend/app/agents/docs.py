"""Docs Agent — RAG поиск + LLM генерация с ФАКТ/ГИПОТЕЗА структурой.

LEGACY — серверный «мозг». Вызывается только через orchestrator из
POST /api/chat (React-админ-панель). В целевой архитектуре это
рассуждение делает Claude по плейбуку ai-lab/skills/SKILL.md, не сервер.
Не развивать.
"""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.models.schemas import ChatMode, ChatResponse, FactItem, SourceRef
from app.rag.retriever import RetrievedChunk, retrieve
from app.storage.sql_db import (
    count_documents,
    get_document,
    get_open_contradictions_for_docs,
    get_open_logic_signals_for_docs,
    get_open_promises_for_docs,
    search_entities_by_query,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты аналитик корпоративной памяти команды Avito. У тебя есть доступ к внутренним \
документам команды — стратегиям, ресёрчам, операционным планам.

ЯЗЫК ОТВЕТА:
- Отвечай ТОЛЬКО на русском языке (кириллица).
- ЗАПРЕЩЕНО использовать китайские/японские/корейские иероглифы.
- Английские термины из документов (CES, TRI*M, MNZ, CPT, ARPPU и т.д.) \
оставляй как есть.

ПРАВИЛА (соблюдай строго):
1. Используй ТОЛЬКО информацию из предоставленных фрагментов документов
2. Каждое фактическое утверждение ОБЯЗАТЕЛЬНО сопровождай ссылкой на источник
3. Разделяй ФАКТЫ (есть в документах) и ГИПОТЕЗЫ (твои предположения)
4. Archived и draft — используй только как контекст с явным предупреждением
5. Если данных недостаточно — напиши это явно, не придумывай

ЧТО СЧИТАЕТСЯ ФАКТОМ:
- Конкретное число с единицей и периодом ("4.2 Bn RUB by CY2030", "TRI*M -12 пунктов")
- Конкретное имя ответственного, команда, или owner инициативы
- Конкретная дата/срок/милстоун с привязкой
- Конкретный пункт roadmap'а со статусом (DONE / In progress / Discovery)
- Цитата из таблицы, appendix или competitor matrix
НЕ являются фактами: общие фразы типа "улучшение поддержки", "повышение качества", \
"оптимизация процессов". Их в facts ставить НЕЛЬЗЯ.

ФОРМАТ ОТВЕТА — строго JSON:
{
  "answer": "Прямой ответ на вопрос в 1-3 предложениях",
  "facts": [
    {
      "statement": "Конкретное утверждение из документа",
      "source_id": 1
    }
  ],
  "hypotheses": ["Предположение которого нет в документах явно"],
  "warnings": ["⚠️ Если использованы archived/draft данные или есть конфликт"],
  "requires_verification": ["Вопрос если данных недостаточно"]
}

source_id — это НОМЕР источника (1, 2, 3...) из заголовка [Источник N] в контексте выше. \
source_id используется ТОЛЬКО внутри объектов facts, как поле "source_id": N. \
В строках answer/hypotheses/warnings/requires_verification ЗАПРЕЩЕНО упоминать \
номера источников вида "[Источник 5]", "Source 7", "(см. 3)" и т.п. — пиши \
название документа или раздел словами, если нужно атрибутировать.

КРИТИЧЕСКОЕ ПРАВИЛО АТРИБУЦИИ: для каждого факта source_id ДОЛЖЕН указывать \
на фрагмент, в заголовке которого стоит ТО ЖЕ название документа, из которого \
факт. Никогда не ставь source_id фрагмента из документа A для факта который \
взят из документа B. Перед тем как поставить source_id, проверь: \
- факт взят из ПОЛНОГО ТЕКСТА или ОБЗОРА документа X? \
- найди в ФРАГМЕНТАХ один с заголовком [Источник N | X | ...]. \
- именно его N ставь в source_id. \
Если в ФРАГМЕНТАХ нет ни одного с подходящим заголовком — не пиши этот факт.

ПРАВИЛА СРАВНЕНИЯ МЕТРИК (важно):
- Помечай как "расхождение" в warnings ТОЛЬКО если одна и та же метрика \
(совпадают имя ИЛИ нормализованное имя), один и тот же период, одна и та же \
единица — имеет разные значения в разных документах.
- Разные метрики с похожим словом в названии (например TRI*M -12 vs CES -16) — \
это НЕ расхождение, это две разные метрики. Не сравнивай их.
- Разные периоды (Q2'25 vs Q4'25) — НЕ расхождение, это эволюция во времени.
- Разные единицы (% vs руб) — НЕ расхождение.

Отвечай ТОЛЬКО валидным JSON. Без markdown-обёртки.\
"""

MODE_INSTRUCTIONS: dict[ChatMode, str] = {
    ChatMode.search: (
        "Найди и синтезируй всё что есть в документах по заданной теме. "
        "Если данных мало — дай что есть и не выдумывай недостающее, "
        "в requires_verification перечисли что не учтено в текущих планах и где "
        "есть риск расхождения плана с реальностью. "
        "Если видишь противоречия в данных — отметь в warnings."
    ),
    ChatMode.contradictions: (
        "Найди числовые и смысловые расхождения по теме между документами. "
        "В facts перечисли разные цифры/тезисы с указанием каждого источника. "
        "В warnings — каждое расхождение отдельной строкой. "
        "Если в базе пока один документ — поищи внутренние нестыковки в нём "
        "(разные значения одной метрики в разных разделах, противоречивые "
        "утверждения). Если нестыковок нет — честно скажи это в answer."
    ),
    ChatMode.promises: (
        "Найди все обещания, планы и дедлайны по теме. "
        "Для каждого: точная цитата, документ, срок если указан, "
        "ответственный если указан. "
        "В warnings — отметь просроченные, без дедлайна, без владельца. "
        "Если обещаний не нашлось — скажи это явно в answer."
    ),
    ChatMode.gaps: (
        "Найди серые зоны: темы которые упомянуты/изучены, но не вошли в "
        "стратегию или план; риски не закрытые мерами; внешние факторы "
        "не учтённые в документах. "
        "В facts — то что обсуждалось но недопроработано. "
        "В requires_verification — что критично проверить. "
        "Если корпус мал, опирайся на здравый смысл и помечай это в hypotheses."
    ),
    ChatMode.write: (
        "Ты помогаешь написать документ. "
        "Собери все релевантные факты из документов для использования в тексте. "
        "В answer — готовый абзац/тезисы под копипаст в стилистике команды."
    ),
    ChatMode.validate: (
        "Оцени инициативу на основе документов. "
        "Укажи: что уже изучали по теме, что противоречит идее, что поддерживает. "
        "В requires_verification — конкретные вопросы которые нужно проверить перед запуском. "
        "В hypotheses — рыночный контекст и аналоги."
    ),
    ChatMode.research: (
        "Это режим РЫНОЧНОГО ИССЛЕДОВАНИЯ — сравнительный разбор внешних "
        "практик с привязкой к нашей задаче.\n\n"
        "❗ ЖЁСТКИЕ ТРЕБОВАНИЯ:\n"
        "1. ОТВЕТ = MARKDOWN-ОТЧЁТ 600-1200 СЛОВ. Одноабзацный summary НЕ "
        "принимается.\n"
        "2. КАЖДУЮ компанию/продукт из ВНЕШНЕГО КОНТЕКСТА ИЗ ИНТЕРНЕТА — "
        "разбери ОТДЕЛЬНОЙ H3 секцией с КОНКРЕТНЫМИ числами/механиками из "
        "web-результатов (стимулы, метрики, сроки, барьеры входа). НЕ пиши "
        "общими фразами — копируй конкретику.\n"
        "3. Inline-ссылки: после каждого факта из web в скобках имя сайта "
        "или короткий URL — например (sell.amazon.com), (pro.wildberries.ru).\n"
        "4. Заверши секцией с практическими паттернами для нашей задачи.\n\n"
        "СТРУКТУРА answer (используй ЭТИ заголовки):\n\n"
        "## Резюме\n3-4 предложения: что сравнивали, главные находки, "
        "ключевой инсайт.\n\n"
        "## [Компания 1]\nДля каждой найденной в web-блоке компании — "
        "отдельная H2 секция (Ozon / Wildberries / Amazon / Shopify / etc). "
        "В каждой:\n"
        "- механика онбординга / обучения / стимулов (с конкретикой)\n"
        "- конкретные цифры (барьеры входа, штрафные баллы, dur периодов, "
        "проценты completion, бонусы, размер инвестиций — что есть в web)\n"
        "- уникальные практики которых нет у других\n"
        "- inline-ссылки на источник\n\n"
        "## [Компания 2]\n...то же самое\n\n"
        "## [Компания 3]\n...то же самое\n\n"
        "## Что отсюда стоит забрать\n"
        "3-6 КОНКРЕТНЫХ паттернов которые можно адаптировать. Каждый пункт:\n"
        "- название механики (выделено **жирным**)\n"
        "- как работает у конкурентов с цифрой эффекта\n"
        "- как переложить на наш контекст (если есть данные из документов "
        "Avito — упомяни их с привязкой)\n\n"
        "ОСТАЛЬНЫЕ ПОЛЯ JSON:\n"
        "- facts: цитаты из ВНУТРЕННИХ документов с source_id (если в "
        "корпусе есть релевантное; если нет — пустой массив)\n"
        "- hypotheses: КАЖДЫЙ web-источник = МИНИМУМ 1 пункт. Начинай с "
        "названия продукта/компании жирным, потом конкретный факт с цифрой "
        "и URL в скобках. Пример: «**Amazon Perfect Launch**: селлеры "
        "которые проходят полный 90-дневный playbook генерируют выручку "
        "в первый год в 6,3 раза больше среднего (sell.amazon.com)».\n"
        "- requires_verification: что подтвердить локальными данными\n\n"
        "НЕ лей воды. Конкретные имена, цифры, цитаты. Каждый web-результат "
        "должен быть использован."
    ),
    ChatMode.full: (
        "Сделай ГЛУБОКИЙ РЕСЁРЧ-ОТЧЁТ. Пользователь ждёт не список цитат, "
        "а полноценный аналитический документ под копипаст в Confluence.\n\n"
        "У ТЕБЯ ДВА ИСТОЧНИКА КОНТЕКСТА:\n"
        "(А) ПОЛНЫЕ ТЕКСТЫ или ОБЗОРЫ документов — первичный источник. "
        "Анализируй ЦЕЛИКОМ каждый документ. Не пропускай таблицы, риски, "
        "appendix, имена, конкретные цифры из ячеек.\n"
        "(Б) ФРАГМЕНТЫ — нумерованные куски для source_id в facts.\n\n"
        "ФОРМАТ ПОЛЯ answer — markdown-отчёт на 800-1500 слов со следующей "
        "структурой (используй именно эти заголовки H2):\n"
        "## Резюме (TL;DR)\n"
        "3-5 предложений: суть, ключевые цифры, статус.\n\n"
        "## Контекст и проблематика\n"
        "Что описано в документах: проблемы, точки боли, причины. Цифры с "
        "единицами и периодами. Цитируй конкретные значения.\n\n"
        "## Ключевые инициативы и направления\n"
        "Структурированный разбор стримов/волн/проектов. Используй подзаголовки "
        "H3 для каждого направления. Указывай владельцев, ожидаемые эффекты, "
        "сроки.\n\n"
        "## Метрики и ожидаемые результаты\n"
        "Таблица или список с цифрами целей. Из каких источников выводы.\n\n"
        "## Риски и расхождения\n"
        "Что может пойти не так, какие риски прямо отмечены в документах "
        "(probability/impact если есть), любые внутренние противоречия.\n\n"
        "## Внешний рыночный контекст и аналоги\n"
        "ОБЯЗАТЕЛЬНО используй свои pretrain-знания об индустрии. Назови "
        "КОНКРЕТНЫЕ продукты, фреймворки, компании с их подходами и метриками. "
        "Примеры что хочется видеть (если релевантно теме):\n"
        "- Маркетплейс-онбординг: Amazon New Seller Guide (6 программ в первые "
        "90 дней), Ozon University, PRO Wildberries, Shopify Magic, Etsy "
        "Education — что и как у них устроено, какие цифры результата.\n"
        "- SaaS-онбординг: Pendo / Appcues / Userpilot — для in-product walkthroughs, "
        "Customer.io / Intercom / Segment — для milestone-based triggers, "
        "Mixpanel / Amplitude — для метрик активации.\n"
        "- Индустриальные benchmarks: типичный onboarding completion в SaaS ~19-20%, "
        "60-70% SaaS-churn в первые 30 дней (Mixpanel/Amplitude reports), "
        "Nielsen Norman Group по UX-стандартам.\n"
        "- Концепты: aha-moment, time-to-first-value, milestone-based vs "
        "time-based triggers, progressive disclosure, empty states as "
        "activation points, Zeigarnik effect для retention.\n"
        "Помечай как hypothesis с disclaimer что это твои знания, не из документов. "
        "Привязывай к данным из документов: «у нас churn 5.5% — это совпадает с "
        "паттерном SaaS «60-70% уходят в первые 30 дней».\n\n"
        "## Рекомендуемый каркас (если уместно)\n"
        "Когда запрос требует ПЛАНА или СТРАТЕГИИ — построй структурированный "
        "каркас (3-5 этапов с aha-moments, метриками и триггерами). Используй "
        "таблицы markdown |Этап|Окно|Aha|Триггеры|Метрика|. Без воды, конкретно.\n\n"
        "## Сегментация (если уместно)\n"
        "Разные подходы для разных сегментов с указанием first-value для каждого.\n\n"
        "## Что сделать прямо сейчас\n"
        "3-5 конкретных действий, которые можно начать БЕЗ нового ресурса, "
        "опираясь на текущие инструменты + изменения в подаче. Не «найти "
        "ресурс», а «перевести welcome-цепочку с time-based на milestone-based — "
        "это CRM-логика, не SX-разработка».\n\n"
        "## Открытые вопросы и серые зоны\n"
        "Что ещё не закрыто, у каких инициатив нет owner/deadline/метрик, "
        "что критично проверить.\n\n"
        "ОСТАЛЬНЫЕ ПОЛЯ JSON:\n"
        "- facts: 10-20 КОНКРЕТНЫХ фактов. Каждый — число с единицей+периодом, "
        "ИЛИ имя ответственного, ИЛИ конкретная дата/deadline, ИЛИ цитата из "
        "таблицы, ИЛИ конкретный статус roadmap'а (DONE/In progress/Not planned). "
        "Общие фразы («улучшение поддержки», «создание центра», «оптимизация») — "
        "НЕ факты, их в facts ставить ЗАПРЕЩЕНО.\n"
        "- По каждому документу минимум 5 фактов.\n"
        "- warnings: список расхождений/рисков отдельной строкой.\n"
        "- hypotheses: ВНЕШНИЕ знания и индустриальные benchmarks из секции "
        "«Внешний рыночный контекст». Каждый пункт начинай со слова продукта/"
        "компании/фреймворка: «Amazon New Seller Guide:...», «Pendo:...», "
        "«Mixpanel reports:...», «Nielsen Norman:...». С disclaimer что это "
        "твои знания.\n"
        "- requires_verification: что не закрыто/не назначено/нужно проверить.\n\n"
        "ПРАВИЛА:\n"
        "- ТОЛЬКО кириллица + английские термины. БЕЗ китайских/японских "
        "иероглифов в тексте.\n"
        "- НЕ округляй цифры, копируй точно из документов.\n"
        "- НЕ выдумывай факты. Где гипотеза — явно пометь.\n"
        "- В answer markdown — используй H2/H3, списки, **жирный** для ключевых "
        "цифр, --- разделители если уместно.\n"
        "- В answer НЕ пиши [Источник N] — пиши название документа.\n"
        "- Если две цифры одной метрики в разных документах — обе в facts + "
        "одна warning о расхождении (только при совпадении period+unit)."
    ),
}


# Режимы, которым нужен ВЕСЬ корпус, а не только retrieve-чанки. Поиск
# числовых/логических расхождений и обещаний по top-15 чанкам слепнет:
# нужная цифра/цитата часто не попадает в retrieval. Если корпус влезает
# в контекст — подаём LLM полные тексты документов целиком.
_FULL_CONTEXT_MODES = frozenset({
    ChatMode.full, ChatMode.contradictions, ChatMode.promises, ChatMode.gaps,
})


def _build_context(chunks: list[RetrievedChunk]) -> str:
    # Сортируем чанки так чтобы фрагменты ОДНОГО документа шли подряд.
    # Без этого LLM может перепутать source_id между документами (фрагменты
    # от B2C идут вперемешку с Education по score), и факты получают
    # неправильную атрибуцию. С группировкой LLM видит "1-15 = doc A,
    # 16-N = doc B" и берёт нужный source_id.
    grouped = sorted(chunks, key=lambda c: (c.document_id or "", c.metadata.get("chunk_index", 0) or 0))
    parts = []
    current_doc = None
    for i, c in enumerate(grouped):
        status_label = c.status.upper()
        level_label = f"L{c.hierarchy_level}"
        title = c.title or c.document_id[:8]
        section = f" / {c.section}" if c.section else ""
        # Видимый разделитель когда меняется документ — помогает LLM не путать
        if c.document_id != current_doc and i > 0:
            parts.append(f"\n### ↓ Следующий документ ↓\n")
        current_doc = c.document_id
        parts.append(
            f"[Источник {i+1} | {title}{section} | {status_label} | {level_label}]\n"
            f"{c.content}"
        )
    # Возвращаем grouped order — index_map в caller'е соответствует именно ему
    return "\n\n---\n\n".join(parts), grouped


def _build_entity_memory_block(
    entities: list,
    contradictions: list,
    logic_signals: list | None = None,
    promises: list | None = None,
) -> str:
    """Формирует блок entity memory для добавления в промпт.

    Помимо метрик и числовых расхождений сюда подмешиваются логические
    сигналы (смысловые противоречия между документами) и незакрытые
    обещания — чтобы система проактивно показывала их в ответе, а не
    держала молча в БД до отдельного запроса на эндпоинт."""
    logic_signals = logic_signals or []
    promises = promises or []
    if not entities and not contradictions and not logic_signals and not promises:
        return ""

    lines = ["[ENTITY MEMORY — известные факты из документов]"]

    if entities:
        lines.append("Метрики и сущности:")
        for e in entities[:25]:
            val = f" = {e.value}" if e.value else ""
            unit = f" {e.unit}" if e.unit else ""
            date = f" ({e.date_context})" if e.date_context else ""
            lines.append(f"  • {e.name}{val}{unit}{date} [doc:{e.document_id[:8]}...]")

    def _loc(id_a: str, id_b: str) -> str:
        # document_id_a == document_id_b → находка внутри одного документа.
        if id_a and id_a == id_b:
            return f"внутри документа {id_a[:8]}"
        return f"doc:{(id_a or '')[:8]} vs doc:{(id_b or '')[:8]}"

    if contradictions:
        lines.append("Известные числовые расхождения по этим документам:")
        for c in contradictions[:25]:
            lines.append(
                f"  ⚠ {c.metric}: {c.value_a} vs {c.value_b} "
                f"[{_loc(c.document_id_a, c.document_id_b)}]"
            )

    if logic_signals:
        lines.append("Известные логические расхождения (смысловые) по этим документам:")
        for s in logic_signals[:15]:
            kind = f"{s.signal_type} · " if s.signal_type else ""
            lines.append(
                f"  ⚠ {kind}«{s.statement_a}» ↔ «{s.statement_b}» "
                f"[{_loc(s.document_id_a, s.document_id_b)}]"
            )

    if promises:
        lines.append("Незакрытые обещания по этим документам:")
        for p in promises[:7]:
            deadline = f", срок {p.deadline}" if p.deadline else ", без срока"
            overdue = " [ПРОСРОЧЕНО]" if p.status == "overdue" else ""
            lines.append(f"  • «{p.text}»{deadline}{overdue} [doc:{p.document_id[:8]}...]")

    lines.append(
        "Если что-то из этих расхождений/обещаний относится к вопросу — "
        "обязательно отрази в warnings отдельной строкой."
    )

    return "\n".join(lines)


async def _parse_llm_response(
    raw: str,
    chunks: list[RetrievedChunk],
    db: AsyncSession,
) -> tuple[str, list[FactItem], list[str], list[str], list[str]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
        text = raw.strip()
        # Снимаем markdown-обёртку ```json ... ```
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    data = None
        if data is None:
            # Спасение: JSON-объект повреждён (LLM иногда ломает синтаксис в
            # длинном answer). Вытаскиваем хотя бы текст answer, чтобы юзер
            # видел осмысленный ответ, а не сырой JSON-дамп.
            am = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
            salvaged = ""
            if am:
                try:
                    salvaged = json.loads('"' + am.group(1) + '"')
                except json.JSONDecodeError:
                    salvaged = am.group(1)
            logger.warning("docs_agent: JSON-объект повреждён, answer спасён частично | head=%r", raw[:200])
            return (
                salvaged or text,                       # answer
                [],                                     # facts
                [],                                     # hypotheses
                ["⚠️ Структурированный ответ повреждён — показан только текст, "
                 "без разбивки на источники"],          # warnings
                [],                                     # requires_verification
                0,                                      # dropped
            )

    # Пост-фильтр: вычищаем артефакты типа [Источник 5] / (Source 7) / [doc:abc]
    # которые LLM иногда вставляет в free-text вопреки правилам в system prompt.
    _src_ref_patterns = [
        re.compile(r"\s*\[Источник\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
        re.compile(r"\s*\(Источник\s*\d+\)", re.IGNORECASE),
        re.compile(r"\s*\[Source\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
        re.compile(r"\s*\(Source\s*\d+\)", re.IGNORECASE),
        re.compile(r"\s*\[doc:[^\]]+\]"),
    ]
    # CJK иероглифы (китайские/японские/корейские) — Moonshot под нагрузкой
    # иногда вставляет их вместо русских слов. Удаляем.
    _cjk_pattern = re.compile(r"[一-鿿぀-ゟ゠-ヿ가-힯]+")

    def _clean_str(s: str) -> str:
        for p in _src_ref_patterns:
            s = p.sub("", s)
        s = _cjk_pattern.sub("", s)
        # Не схлопываем переводы строк — нужны для markdown в answer
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    def _as_str_list(raw):
        # LLM иногда возвращает элементы как dict {statement, source_id} —
        # схема ждёт строки, приводим вручную. Заодно вычищаем артефакты
        # source-ссылок в свободном тексте.
        out = []
        for w in raw or []:
            if not w:
                continue
            if isinstance(w, str):
                cleaned = _clean_str(w)
            elif isinstance(w, dict):
                raw_str = w.get("statement") or w.get("text") or str(w)
                cleaned = _clean_str(raw_str)
            else:
                cleaned = _clean_str(str(w))
            if cleaned:
                out.append(cleaned)
        return out

    answer = _clean_str(data.get("answer", ""))
    hypotheses = _as_str_list(data.get("hypotheses"))
    warnings = _as_str_list(data.get("warnings"))
    requires = _as_str_list(data.get("requires_verification"))

    # Индексный map: номер источника (1-based) → chunk
    index_map: dict[int, RetrievedChunk] = {i + 1: c for i, c in enumerate(chunks)}

    facts: list[FactItem] = []
    unsupported_count = 0
    for f in data.get("facts", []):
        if not isinstance(f, dict) or not f.get("statement"):
            continue

        # source_id теперь целое число — номер источника
        try:
            source_num = int(f.get("source_id", 0))
        except (TypeError, ValueError):
            source_num = 0
        chunk = index_map.get(source_num)

        # Программная проверка: подтверждается ли утверждение чанком-источником?
        # Если LLM сослался на чанк который не содержит ключевых токенов
        # утверждения — это галлюцинация, факт отбрасываем.
        if chunk:
            from app.skills.grounding import is_grounded
            ok, reason = is_grounded(f["statement"], chunk.content or "")
            if not ok:
                unsupported_count += 1
                logger.info("grounding: drop fact (%s): %s",
                            reason, f["statement"][:80])
                continue

        if chunk:
            doc_row = await get_document(db, chunk.document_id)
            # SourceRef.document_id типизирован как UUID, а в Chroma могли
            # попасть не-UUID id (старые тестовые прогоны и т.п.) — подменяем
            # на nil-UUID и сохраняем оригинал в title.
            from uuid import UUID as _UUID
            try:
                doc_uuid = _UUID(str(chunk.document_id))
            except (TypeError, ValueError):
                doc_uuid = _UUID("00000000-0000-0000-0000-000000000000")
            source = SourceRef(
                document_id=doc_uuid,
                title=doc_row.title if doc_row else (chunk.title or chunk.document_id),
                status=chunk.status,  # type: ignore[arg-type]
                hierarchy_level=chunk.hierarchy_level,
                section=chunk.section or None,
                confluence_url=doc_row.confluence_url if doc_row else None,
            )
        else:
            # Если LLM не дал валидный номер — ставим заглушку, не теряем факт
            from uuid import UUID as _UUID
            source = SourceRef(
                document_id=_UUID("00000000-0000-0000-0000-000000000000"),
                title="Источник не определён",
                status="unknown",  # type: ignore[arg-type]
                hierarchy_level=5,
            )

        facts.append(FactItem(statement=f["statement"], source=source))

    # Если значимая часть фактов не подтверждена — предупреждаем пользователя.
    # Это даёт сигнал «модель пыталась галлюцинировать, мы отфильтровали».
    if unsupported_count > 0:
        warnings.insert(
            0,
            f"⚠️ Отфильтровано {unsupported_count} утверждений: "
            f"не подтверждены содержимым источников (защита от галлюцинаций)",
        )

    return answer, facts, hypotheses, warnings, requires, unsupported_count


async def run(
    message: str,
    mode: ChatMode,
    file_content: str | None = None,
    db: AsyncSession | None = None,
    history=None,
    style: str = "report",
    force_retrieval: bool = False,
) -> dict:
    # Поиск релевантных чанков — для full режима берём больше материала,
    # чтобы LLM мог достать конкретные числа и атрибуцию.
    include_archive = mode in (ChatMode.search, ChatMode.gaps, ChatMode.contradictions)
    top_k = 30 if mode == ChatMode.full else 15

    # Для full-режима пытаемся декомпозировать составной запрос — если он
    # реально составной, пройдёмся retrieval'ом по каждому под-вопросу и
    # объединим результаты. Это даёт более полное покрытие на запросах
    # вида "сначала X, потом Y, потом план".
    chunks = []
    sub_queries: list[str] = []
    # query_planner полезен на любом синтетическом mode + длинном запросе,
    # а не только full. search/research тоже выигрывают от мульти-извлечения.
    msg_lc = message.lower()
    multi_signals = (
        len(message) > 100
        or any(t in msg_lc for t in (" и ", " а также ", " затем ", " потом ", " также ", "сначала"))
    )
    if mode in (ChatMode.full, ChatMode.search, ChatMode.research) and multi_signals:
        try:
            from app.skills.query_planner import decompose
            sub_queries = await decompose(message)
        except Exception as exc:
            logger.warning("query_planner failed (skipping): %s", exc)
            sub_queries = []

    if sub_queries:
        # По каждому под-запросу берём меньше top_k. При дубле сохраняем
        # ЛУЧШИЙ score (max), чтобы итоговая сортировка отражала «насколько
        # релевантно для всех под-запросов» — chunk встречающийся в 2 sub-q
        # = более релевантный.
        per_sub = max(8, top_k // max(1, len(sub_queries)))
        by_id: dict[str, "RetrievedChunk"] = {}
        for sq in [message] + sub_queries:
            try:
                sub_chunks = await retrieve(sq, top_k=per_sub, include_archive=include_archive)
            except Exception as exc:
                logger.warning("retrieve failed for sub-query: %s", exc)
                continue
            for c in sub_chunks:
                existing = by_id.get(c.id)
                if existing is None or (c.score or 0) > (existing.score or 0):
                    by_id[c.id] = c
        chunks = sorted(by_id.values(), key=lambda c: -(c.score or 0))[:top_k + 10]
        logger.info("planner-retrieval: %d sub-queries → %d unique chunks",
                    len(sub_queries), len(chunks))
    else:
        chunks = await retrieve(message, top_k=top_k, include_archive=include_archive)

    # Document-level контекст для full mode имеет 3 стратегии в зависимости
    # от размера корпуса:
    #   1) корпус влезает целиком (≤200K chars ≈ 50K токенов) → ПОЛНЫЕ ТЕКСТЫ
    #   2) средний (≤30 доков, не помещается) → ОБЗОРЫ (briefs)
    #   3) большой (>30 доков или брифов > 100K chars) → deep_research:
    #      router выбирает топ-N, потом iterative refinement по их полным
    #      текстам, потом synthesis. Возвращаем результат deep_research как
    #      финальный ответ, минуя обычный LLM-вызов в этой функции.
    doc_briefs_block = ""
    full_texts_block = ""
    if mode in _FULL_CONTEXT_MODES and db is not None and not force_retrieval:
        # 200K символов ≈ 50K токенов — с запасом влезает в 200K-контекст
        # Claude вместе с system-промптом, чанками и entity-memory.
        FULL_TEXTS_BUDGET = 200_000

        from app.storage.sql_db import (
            get_all_document_briefs,
            get_all_document_full_texts,
        )
        # actual + unknown: загруженные через upload документы по умолчанию
        # имеют статус "unknown", но их чанки уже лежат в actual-коллекции
        # (_collection_for_status). Без "unknown" full-mode их бы не видел.
        full_texts = await get_all_document_full_texts(
            db, statuses=["actual", "unknown"], limit=20)
        total = sum(len(t) for _, t in full_texts)
        n_docs = len(full_texts)

        # Стратегия 1: всё влезает — даём полные тексты LLM напрямую
        if full_texts and total <= FULL_TEXTS_BUDGET and n_docs <= 20:
            parts = [
                f"=== ПОЛНЫЙ ТЕКСТ: {doc.title} (L{doc.hierarchy_level or 5}, {doc.status}) ===\n{text}"
                for doc, text in full_texts
            ]
            full_texts_block = "\n\n".join(parts)
            logger.info("full-mode: using %d full texts (%d chars total)", n_docs, total)
        else:
            # Стратегия 2 vs 3: проверяем сколько brief'ов есть
            briefs = await get_all_document_briefs(
                db, statuses=["actual", "unknown"], limit=500)
            briefs_total = sum(len(b) for _, b in briefs)

            # Стратегия 3: корпус большой — переходим в deep_research.
            # Только для full-режима: contradictions/promises/gaps не должны
            # уходить в deep_research-ветку с ранним return.
            DEEP_DOC_THRESHOLD = 20
            if mode == ChatMode.full and (
                len(briefs) > DEEP_DOC_THRESHOLD or briefs_total > 100_000
            ):
                from app.skills.deep_research import run_deep_research
                logger.info("full-mode: switching to deep_research (%d docs, %d brief chars)",
                            len(briefs), briefs_total)
                context_chunks, _ = _build_context(chunks)
                deep_result = await run_deep_research(
                    query=message,
                    db=db,
                    chunks_context=context_chunks,
                    max_docs=10,
                )
                # Превратим plain dict в FactItem'ы используя index_map
                facts: list[FactItem] = []
                index_map: dict[int, RetrievedChunk] = {i + 1: c for i, c in enumerate(chunks)}
                for f in deep_result.get("facts", []):
                    if not isinstance(f, dict) or not f.get("statement"):
                        continue
                    try:
                        source_num = int(f.get("source_id", 0))
                    except (TypeError, ValueError):
                        source_num = 0
                    chunk = index_map.get(source_num)
                    from uuid import UUID as _UUID
                    if chunk:
                        doc_row = await get_document(db, chunk.document_id)
                        try:
                            doc_uuid = _UUID(str(chunk.document_id))
                        except (TypeError, ValueError):
                            doc_uuid = _UUID("00000000-0000-0000-0000-000000000000")
                        source = SourceRef(
                            document_id=doc_uuid,
                            title=doc_row.title if doc_row else (chunk.title or chunk.document_id),
                            status=chunk.status,  # type: ignore[arg-type]
                            hierarchy_level=chunk.hierarchy_level,
                            section=chunk.section or None,
                            confluence_url=doc_row.confluence_url if doc_row else None,
                        )
                    else:
                        source = SourceRef(
                            document_id=_UUID("00000000-0000-0000-0000-000000000000"),
                            title="Источник не определён",
                            status="unknown",  # type: ignore[arg-type]
                            hierarchy_level=5,
                        )
                    facts.append(FactItem(statement=f["statement"], source=source))

                return {
                    "answer": deep_result.get("answer", ""),
                    "facts": facts,
                    "hypotheses": deep_result.get("hypotheses", []) or [],
                    "warnings": deep_result.get("warnings", []) or [],
                    "requires_verification": deep_result.get("requires_verification", []) or [],
                    "agents_used": ["docs", "deep_research"],
                    "chunks_used": len(chunks),
                    "coverage": {
                        "context_mode": "deep_research",
                        "documents_in_context": len(briefs),
                        "chunks_retrieved": len(chunks),
                    },
                    "facts_dropped": 0,
                    "facts_kept": len(facts),
                }

            # Стратегия 2: брифы влезают, тексты — нет
            if briefs:
                parts = [f"=== ОБЗОР ДОКУМЕНТА: {doc.title} (L{doc.hierarchy_level or 5}) ===\n{brief}"
                         for doc, brief in briefs]
                doc_briefs_block = "\n\n".join(parts)
                logger.info("full-mode: corpus too big (%d full chars), using %d briefs (%d chars)",
                            total, len(briefs), briefs_total)

    # Entity memory — обогащаем контекст релевантными сущностями, числовыми
    # расхождениями, логическими сигналами и незакрытыми обещаниями.
    entity_block = ""
    if db is not None:
        keywords = [w for w in message.split() if len(w) > 3]
        entities = await search_entities_by_query(db, keywords, limit=20)
        doc_ids = list({c.document_id for c in chunks})
        contradictions_in_scope = await get_open_contradictions_for_docs(db, doc_ids)
        logic_signals_in_scope = await get_open_logic_signals_for_docs(db, doc_ids)
        promises_in_scope = await get_open_promises_for_docs(db, doc_ids)
        entity_block = _build_entity_memory_block(
            entities,
            contradictions_in_scope,
            logic_signals_in_scope,
            promises_in_scope,
        )

    # Если загружен файл — добавляем его текст к запросу
    extra_context = ""
    if file_content:
        extra_context = f"\n\n[ЗАГРУЖЕННЫЙ ДОКУМЕНТ ДЛЯ АНАЛИЗА]\n{file_content[:4000]}"

    context, chunks = _build_context(chunks)
    mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS[ChatMode.search])

    # Режим контекста — для метрики охвата ответа (ТЗ v1.4 §13.4).
    if full_texts_block:
        knowledge_section = (
            "\n\nПОЛНЫЕ ТЕКСТЫ ДОКУМЕНТОВ (анализируй ВСЁ что есть, не упускай детали):\n"
            + full_texts_block + "\n"
        )
        context_mode = "full_texts"
        docs_in_context = full_texts_block.count("=== ПОЛНЫЙ ТЕКСТ")
    elif doc_briefs_block:
        knowledge_section = (
            "\n\nОБЗОРЫ ВСЕХ ДОКУМЕНТОВ В БАЗЕ (для общей картины каждого дока):\n"
            + doc_briefs_block + "\n"
        )
        context_mode = "briefs"
        docs_in_context = doc_briefs_block.count("=== ОБЗОР ДОКУМЕНТА")
    else:
        knowledge_section = ""
        context_mode = "retrieval"
        docs_in_context = len({c.document_id for c in chunks})

    # Web search — для full mode если запрос требует «внешнего опыта» И
    # Web search — для full / research режимов когда запрос требует
    # «внешнего опыта» И настроен один из API-ключей (Tavily/Brave).
    # research → multi-query (3-5 целевых поисков по компаниям/концептам).
    # full → single-query (контекста из документов и так много).
    web_section = ""
    web_warning: str | None = None  # покажем юзеру если поиск был нужен но не вышел
    if mode in (ChatMode.full, ChatMode.research):
        from app.settings import settings as _settings
        web_keys_configured = bool(_settings.TAVILY_API_KEY or _settings.BRAVE_API_KEY)
        try:
            from app.skills.web_research import (
                should_do_web_search, do_research, do_research_multi,
            )
            if mode == ChatMode.research:
                if not web_keys_configured:
                    web_warning = (
                        "⚠️ Режим «Рынок» работает без подключённого web-поиска "
                        "(нет TAVILY_API_KEY / BRAVE_API_KEY в .env). "
                        "Используются только знания LLM из pretrain."
                    )
                    web_block = ""
                else:
                    web_block = await do_research_multi(message, max_results_per_query=10)
                    if not web_block:
                        web_warning = (
                            "⚠️ Внешний поиск не вернул результатов. "
                            "Возможно квота исчерпана или сеть недоступна."
                        )
            elif should_do_web_search(message):
                if web_keys_configured:
                    web_block = await do_research(message, max_results=5)
                else:
                    web_block = ""
            else:
                web_block = ""
            if web_block:
                web_section = "\n\n" + web_block + "\n"
                logger.info("web_research: injected %d chars", len(web_block))
        except Exception as exc:
            logger.warning("web_research error (skipping): %s", exc)
            web_warning = f"⚠️ Веб-поиск не сработал: {exc}"

    # История диалога — для follow-up'ов и местоимений
    history_section = ""
    if history:
        lines = []
        for m in list(history)[-6:]:
            role = "User" if m.role == "user" else "Assistant"
            content = (m.content or "").strip()
            if len(content) > 600:
                content = content[:600] + "..."
            lines.append(f"[{role}] {content}")
        if lines:
            history_section = (
                "\n\nИСТОРИЯ ДИАЛОГА (последние сообщения, используй для понимания "
                "контекста и follow-up вопросов):\n" + "\n".join(lines) + "\n"
            )

    # Подсказка по стилю — поверх mode_instruction
    style_hint = {
        "report": "Стиль: длинный markdown-отчёт с разделами H2.",
        "list": "Стиль: компактный список с подзаголовками H3 для группировки.",
        "short": "Стиль: короткий ответ 1-3 абзаца. Без длинных разделов.",
        "plan": "Стиль: пошаговый план — пронумерованный список шагов с описанием.",
        "qa": "Стиль: формат «Вопрос — Ответ» с короткими блоками.",
    }.get(style, "")

    user_message = (
        f"Режим: {mode.value}\n"
        f"Инструкция: {mode_instruction}\n"
        + (f"{style_hint}\n" if style_hint else "")
        + history_section
        + knowledge_section
        + web_section
        + f"\nФРАГМЕНТЫ ДОКУМЕНТОВ (для точных цитат с source_id):\n{context}"
        + (f"\n\n{entity_block}" if entity_block else "")
        + extra_context
        + f"\n\nВОПРОС: {message}"
    )

    # full mode требует длинного markdown-отчёта (1500 слов ≈ 2K tokens) + 20 фактов
    # JSON (~2K tokens). 4096 не хватает — поднимаем до 8000 для full.
    # Full и Research возвращают длинный markdown + facts JSON — нужен запас.
    max_tokens = 8000 if mode in (ChatMode.full, ChatMode.research) else 4096
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("docs_agent: LLM call failed: %s", e)
        return {
            "answer": "",
            "facts": [],
            "hypotheses": [],
            "warnings": [f"⚠️ Ошибка обращения к LLM: {e}"],
            "requires_verification": [],
            "chunks_used": len(chunks),
            "agents_used": ["docs"],
        }

    answer, facts, hypotheses, warnings, requires, dropped = await _parse_llm_response(
        raw, chunks, db
    )

    agents = ["docs"]

    # Видимый план — prepend к answer как blockquote, чтобы UX был похож на
    # «агент работает», а не «ждите 60 сек». Только для full mode где это
    # имеет смысл.
    if mode in (ChatMode.full, ChatMode.research) and answer:
        try:
            from app.skills.plan_announcer import announce_plan
            doc_titles = sorted({(c.title or c.document_id[:8]) for c in chunks})
            plan_text = await announce_plan(message, doc_titles)
            if plan_text:
                answer = f"> 🔬 {plan_text}\n\n{answer}"
                agents.append("plan_announcer")
        except Exception as exc:
            logger.warning("plan_announcer error (skipping): %s", exc)

    # Self-correction только для full mode и только когда критика реально
    # серьёзная. Регенерация — последний шанс улучшить ответ, если станет
    # хуже — откатываем.
    _NIL_UUID = "00000000-0000-0000-0000-000000000000"

    def _valid_facts_count(fact_list) -> int:
        """Считает только факты с реальной атрибуцией (не nil UUID)."""
        n = 0
        for f in fact_list or []:
            src = getattr(f, "source", None)
            if src is None:
                continue
            doc_id = str(getattr(src, "document_id", ""))
            if doc_id and doc_id != _NIL_UUID:
                n += 1
        return n

    if mode == ChatMode.full and chunks:
        try:
            from app.skills.self_check import critique
            payload = {
                "answer": answer,
                "facts": facts,
                "hypotheses": hypotheses,
                "warnings": warnings,
                "requires_verification": requires,
            }
            crit = await critique(message, payload, context)
            issues = crit.get("issues") or []
            missing = crit.get("missing_facts") or []
            # Регенерируем только если critique вернул >=2 проблем ИЛИ >=3
            # пропущенных факта. Иначе цена регенерации > пользы.
            serious = (not crit.get("ok", True)) and (len(issues) >= 2 or len(missing) >= 3)
            if serious:
                logger.info("self_check: regenerating with %d issues, %d missing",
                            len(issues), len(missing))
                feedback = (
                    "\n\nКРИТИКА ПРЕДЫДУЩЕЙ ВЕРСИИ ОТВЕТА (исправь эти проблемы, "
                    "но сохрани формат: source_id в facts должен быть ЦЕЛЫМ ЧИСЛОМ "
                    "из заголовков [Источник N] в ФРАГМЕНТАХ выше):\n"
                    + "\n".join(f"- {i}" for i in issues)
                    + (
                        "\n\nКЛЮЧЕВЫЕ ФАКТЫ КОТОРЫЕ НУЖНО ДОБАВИТЬ:\n"
                        + "\n".join(f"- {f}" for f in missing)
                        if missing else ""
                    )
                )
                raw2 = await call_llm(
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message + feedback}],
                    max_tokens=max_tokens,
                )
                ans2, facts2, hyp2, warn2, req2, drop2 = await _parse_llm_response(raw2, chunks, db)
                # Принимаем регенерацию только если она НЕ ухудшила атрибуцию.
                # Часто регенерация ломает source_id mapping (LLM забывает что
                # это число) — все факты валятся в nil UUID. Откат.
                valid_before = _valid_facts_count(facts)
                valid_after = _valid_facts_count(facts2)
                if ans2 and valid_after >= max(1, valid_before - 1):
                    answer, facts, hypotheses, warnings, requires = ans2, facts2, hyp2, warn2, req2
                    dropped = drop2
                    agents.append("self_check")
                    logger.info("self_check: accepted (valid sources %d → %d)",
                                valid_before, valid_after)
                else:
                    logger.info("self_check: rejected regeneration (valid sources "
                                "%d → %d, would degrade)", valid_before, valid_after)
        except Exception as exc:
            logger.warning("self_check pipeline error (skipping): %s", exc)

    # Предупреждение если web-поиск был ожидаем но не вышел
    if web_warning:
        warnings.append(web_warning)

    # Предупреждение если нет чанков
    if not chunks:
        warnings.append("⚠️ Релевантных документов по данному запросу не найдено")

    # Предупреждение об archived чанках
    archive_chunks = {c.document_id: c for c in chunks if c.status == "archived"}
    for doc_id, c in archive_chunks.items():
        label = c.title or doc_id[:8]
        warnings.append(f"⚠️ Использованы данные из архивного документа «{label}»")

    # Охват проверки (ТЗ v1.4 §13.4) — ответ не выдаётся без указания, сколько
    # документов реально просмотрено. В retrieval-режиме это явно в warnings,
    # чтобы «расхождений нет» не означало «посмотрел 5% корпуса».
    documents_total = await count_documents(db) if db is not None else 0
    coverage = {
        "context_mode": context_mode,
        "documents_total": documents_total,
        "documents_in_context": docs_in_context,
        "chunks_retrieved": len(chunks),
    }
    if context_mode == "retrieval":
        warnings.append(
            f"⚠️ Охват: просмотрено {docs_in_context} документов из "
            f"{documents_total} через retrieval ({len(chunks)} фрагментов) — "
            f"возможны находки за пределами выборки"
        )

    return {
        "answer": answer,
        "facts": facts,
        "hypotheses": hypotheses,
        "warnings": warnings,
        "requires_verification": requires,
        "chunks_used": len(chunks),
        "agents_used": agents,
        "coverage": coverage,
        "facts_dropped": dropped,
        "facts_kept": len(facts),
    }
