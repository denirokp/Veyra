# Eval seed — cross-document findings

Первый размеченный кейс-сет для оценки детекторов Хроники (фаза 2).
Получен ручным кросс-документным анализом трёх реальных документов
коммерческого блока. Каждый кейс — ожидаемая находка с трассировкой
к источнику; против него меряется precision/recall детектора.

## Корпус кейс-сета

| ID | Документ | Дата | Файл |
|----|----------|------|------|
| D1 | P&S Progress review 2025 & Action Plan 2026 | 24.10.2025 | Progress_plan_CY25_and_PS_action_plan_CY26 |
| D2 | Pro sellers' education strategy | 27.03.2025 | ENG_Sellers_education_strategy_2025_3.0 |
| D3 | B2C Journey — Deep Dive | April 2026 | B2C_Journey_Deep_Dive_April_2026 |

Документы писали пересекающиеся команды (Alina Staruk — во всех трёх;
Aleksey Li — спонсор D2, автор D3). Это условие, при котором
кросс-документный дрейф возникает и не ловится вручную.

---

## Логические противоречия

### L-01 — противоположный нарратив здоровья PRO-сегмента
- **Тип:** logic_contradiction
- **Документы:** D1 ↔ D3
- **Ожидаемая находка:** один и тот же PRO-сегмент за 2025 год описан
  как растущий (D1) и как падающий (D3).
- **D1, Executive summary / FAQ-1:** «based on the results of 2025, we
  are achieving the target P&S metrics in the PRO segments»; YoY
  Accepted items +39%, Trx revenue +74%, GMV +41%.
- **D3, Executive summary:** «the active CPA PRO-seller base dropped by
  6% (271k→255k), reversing the steady growth seen before Q3'25»;
  «−19k sellers' churn per month in 2025 led to −7.5% / −1,3 Bn Rub losses».
- **Разрешение:** совместимо технически (выручка растёт при сжатии базы
  за счёт take-rate), но стратегические нарративы противоположны и не сведены.
- **Confidence:** high

### L-02 — «#1 platform to start a business»: утверждаемый факт vs цель-2028
- **Тип:** logic_contradiction
- **Документы:** D2 ↔ D3
- **Ожидаемая находка:** D2 транслирует позиционирование как факт,
  D3 трактует его как недостигнутую цель и приводит опровергающие данные.
- **D2, FAQ-3 / Appendix 10:** message «Avito is the #1 platform for
  starting an online business» — основа стратегии обучения продавцов.
- **D3, FAQ-2 / Table 2:** Wave 3 (CY2028) goal — «Recognized by sellers
  as the #1 platform to start and conduct business»; CES Avito 39 vs
  Ozon 77 / WB 77; «nearly 2 times lower in seller satisfaction».
- **Confidence:** high

### L-03 — CPT-тариф: драйвер роста vs механика оттока
- **Тип:** logic_contradiction
- **Документы:** D1 ↔ D3
- **Ожидаемая находка:** разные команды по-разному оценивают одну
  тарифную механику.
- **D1, FAQ-2 / Table 4 / Appendix 1:** масштабирование CPT и гибридного
  тарифа CPC+CPT как приоритетный левередж продаж 2026.
- **D3, FAQ-1.2:** «CPT tariff is not publicly available… offered only
  when it becomes economically beneficial for us or after a seller
  churns… used by only 2.5% of PRO sellers. Many sellers intentionally
  churn from the CPC model… to gain access to CPT».
- **Confidence:** medium

---

## Числовые противоречия

### N-01 — отток PRO-продавцов 2025, расхождение внутри D3
- **Тип:** numeric_contradiction
- **Документы:** D3 (intra-document)
- **Метрика:** среднемесячный отток PRO-продавцов, 2025
- **Значение A:** −19k/мес — D3 Executive summary («−19k sellers'
  churn per month in 2025»)
- **Значение B:** −23k/мес — D3 Appendix 2, traction model
  («Churn AVG: 2024A −19, 2025A −23»)
- **Примечание:** −19k в саммари совпадает со строкой 2024, не 2025.
- **Confidence:** high

### N-02 — churn rate, расхождение внутри D3 (вход финмодели)
- **Тип:** numeric_contradiction
- **Документы:** D3 (intra-document)
- **Метрика:** churn rate PRO-продавцов
- **Значение A:** 7% — D3 FAQ-1.1 («7% seller churn vs 6.5% new client growth»)
- **Значение B:** 5,54% — D3 Appendix 2, константа traction-модели
- **Значимость:** 5,54% зашит во весь прогноз +4,2 млрд руб; модель
  считает по оттоку ниже декларируемого текущего.
- **Confidence:** high

### N-03 — прогноз дохода от обучения, расхождение D2 ↔ D3
- **Тип:** numeric_contradiction (слабый сигнал)
- **Документы:** D2 ↔ D3
- **Метрика:** ожидаемый доход от обучающего/SX-потока
- **Значение A:** +72 млн руб за 2 года — D2 FAQ-2
- **Значение B:** +1 141 млн руб к CY'30 — D3 FAQ-1 / Appendix 1
- **Примечание:** разные горизонты и скоуп; ~16x расхождения — повод
  свести, не жёсткое противоречие.
- **Confidence:** low

---

## Обещания vs сделано

### P-01 — обучающая платформа: обещана 2025, не существует 2026
- **Тип:** promise / undelivered
- **Документы:** D2 (обещание) → D3 (статус)
- **Обещание (D2, 27.03.2025):** перезапуск Business School / обучающей
  платформы — стержень стратегии; «budget allocated»; roadmap с
  запусками контента в 2025.
- **Факт (D3, April 2026):** «No educational platform» (Appendix 1);
  «Proprietary training platform: Avito 🔴 — No proprietary platform.
  Only FAQ/Help»; «content is highly fragmented».
- **Ожидаемая находка:** обязательство D2 не выполнено за год.
- **Confidence:** high

---

## Серые зоны

### G-01 — education-поток без выделенных ресурсов в течение года
- **Тип:** gap
- **Документы:** D2 → D3
- **D2, FAQ-5:** запрос центра экспертизы по обучению + 2 новых FTE
  (Education stream leader, PM Content — оба «new»); спонсор — Aleksey Li.
- **D3, FAQ-2 / FAQ-5:** «the SX team… due to the absence of dedicated
  resources, we have no confirmation for its development»; next steps —
  «Find resources for SX & Education stream (Support needed)».
- **Ожидаемая находка:** поток, инициированный в марте 2025, к апрелю
  2026 всё ещё не укомплектован — провален между приоритетами.
- **Подтверждение:** D3 сам признаёт — «Earlier, we made multiple
  attempts to push initiatives, but they were consistently deprioritized».
- **Confidence:** high

### G-02 — D1 не отразил уже идущий отток PRO-продавцов
- **Тип:** gap
- **Документы:** D1, сверка с D3
- **Ожидаемая находка:** D1 (24.10.2025) написан с позиции «достигаем
  целей» и не отмечает риск оттока/падения satisfaction PRO-продавцов
  как стратегическую угрозу.
- **D3** датирует начало спада «before Q3'25» / «from June'25» — то есть
  к моменту написания D1 сигнал уже шёл, но в обзор не попал.
- **Confidence:** medium

---

## Сводка

| ID | Тип | Документы | Confidence |
|----|-----|-----------|------------|
| L-01 | logic_contradiction | D1 ↔ D3 | high |
| L-02 | logic_contradiction | D2 ↔ D3 | high |
| L-03 | logic_contradiction | D1 ↔ D3 | medium |
| N-01 | numeric_contradiction | D3 intra | high |
| N-02 | numeric_contradiction | D3 intra | high |
| N-03 | numeric_contradiction | D2 ↔ D3 | low |
| P-01 | promise / undelivered | D2 → D3 | high |
| G-01 | gap | D2 → D3 | high |
| G-02 | gap | D1 (vs D3) | medium |

Метод: ручной кросс-документный анализ (Claude напрямую, не задеплоенный
пайплайн — в окружении нет ключей/Chroma). Извлечение из .docx схлопывает
таблицы в плоские строки; на проде нужна table-aware разметка.
