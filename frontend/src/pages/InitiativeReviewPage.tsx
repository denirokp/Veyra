import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { reviewInitiative } from '../api/client'
import type {
  InitiativeReviewResult,
  InitiativeAnchor,
  InitiativeConflict,
  InitiativeGap,
  InitiativeAnalogue,
} from '../types'
import clsx from 'clsx'

const VERDICT_CONFIG = {
  approve: { label: 'Одобрить', color: 'bg-emerald-900/60 text-emerald-300 border-emerald-700' },
  needs_work: { label: 'Требует доработки', color: 'bg-yellow-900/60 text-yellow-300 border-yellow-700' },
  reject: { label: 'Отклонить', color: 'bg-red-900/60 text-red-300 border-red-700' },
}

const ALIGN_COLOR = {
  supports: 'text-emerald-400',
  neutral: 'text-zinc-400',
  conflicts: 'text-red-400',
}

const ALIGN_ICON = { supports: '↑', neutral: '→', conflicts: '✗' }

const GAP_TYPE_LABEL: Record<string, string> = {
  metric: 'Метрика',
  owner: 'Владелец',
  deadline: 'Дедлайн',
  resource: 'Ресурсы',
  market_validation: 'Рынок',
}

const SEVERITY_COLOR = {
  high: 'bg-red-900/50 text-red-300',
  medium: 'bg-yellow-900/50 text-yellow-300',
  low: 'bg-zinc-700 text-zinc-400',
}

function Section({ title, children, empty }: { title: string; children: React.ReactNode; empty?: boolean }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">{title}</h3>
      {empty ? (
        <p className="text-sm text-zinc-600 italic">Нет данных</p>
      ) : (
        children
      )}
    </div>
  )
}

function AnchorCard({ a }: { a: InitiativeAnchor }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-zinc-200">{a.title}</span>
        <span className={clsx('text-sm font-bold shrink-0', ALIGN_COLOR[a.alignment])}>
          {ALIGN_ICON[a.alignment]}
        </span>
      </div>
      <p className="text-xs text-zinc-400 leading-snug">{a.relevance}</p>
    </div>
  )
}

function ConflictCard({ c }: { c: InitiativeConflict }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-3 space-y-1">
      <div className="flex items-center gap-2">
        <span className={clsx('text-xs px-1.5 py-0.5 rounded', SEVERITY_COLOR[c.severity])}>
          {c.severity}
        </span>
        {c.source && <span className="text-xs text-zinc-500">{c.source}</span>}
      </div>
      <p className="text-sm text-zinc-200 leading-snug">{c.description}</p>
    </div>
  )
}

function GapBadge({ g }: { g: InitiativeGap }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-3 space-y-1">
      <span className="text-xs font-medium text-orange-400">
        {GAP_TYPE_LABEL[g.gap_type] ?? g.gap_type}
      </span>
      <p className="text-sm text-zinc-300 leading-snug">{g.description}</p>
    </div>
  )
}

function AnalogueCard({ a }: { a: InitiativeAnalogue }) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-3 space-y-1">
      <div className="text-sm font-medium text-zinc-200">{a.title}</div>
      {a.outcome && <p className="text-xs text-zinc-400">Итог: {a.outcome}</p>}
      {a.lesson && <p className="text-xs text-blue-400 italic">Урок: {a.lesson}</p>}
    </div>
  )
}

function ReviewResult({ result }: { result: InitiativeReviewResult }) {
  const verdict = VERDICT_CONFIG[result.recommendation.verdict]
  return (
    <div className="space-y-6">
      {/* Вердикт */}
      <div className={clsx('rounded-xl border p-4 space-y-2', verdict.color)}>
        <div className="flex items-center gap-3">
          <span className="text-base font-bold">{verdict.label}</span>
          <span className="text-xs opacity-70">
            {result.metadata.chunks_used} чанков · {result.metadata.contradictions_found} расхождений · {result.metadata.logic_signals_found} сигналов
          </span>
        </div>
        <p className="text-sm leading-relaxed opacity-90">{result.recommendation.reasoning}</p>
      </div>

      {/* Блок 1: Суть */}
      <Section title="1. Суть инициативы">
        <p className="text-sm text-zinc-200 leading-relaxed">{result.summary}</p>
      </Section>

      {/* Блок 2: Стратегические якоря */}
      <Section
        title="2. Стратегические документы"
        empty={result.strategic_anchors.length === 0}
      >
        <div className="space-y-2">
          {result.strategic_anchors.map((a, i) => <AnchorCard key={i} a={a} />)}
        </div>
      </Section>

      {/* Блок 3: Конфликты */}
      <Section
        title="3. Сигналы к проверке"
        empty={result.conflicts.length === 0}
      >
        <div className="space-y-2">
          {result.conflicts.map((c, i) => <ConflictCard key={i} c={c} />)}
        </div>
      </Section>

      {/* Блок 4: Пробелы */}
      <Section
        title="4. Что не хватает"
        empty={result.gaps.length === 0}
      >
        <div className="grid grid-cols-1 gap-2">
          {result.gaps.map((g, i) => <GapBadge key={i} g={g} />)}
        </div>
      </Section>

      {/* Блок 5: Аналоги */}
      <Section
        title="5. Аналоги в корпусе"
        empty={result.analogues.length === 0}
      >
        <div className="space-y-2">
          {result.analogues.map((a, i) => <AnalogueCard key={i} a={a} />)}
        </div>
      </Section>

      {/* Блок 6: Внешний контекст */}
      <Section title="6. Внешний контекст">
        <p className="text-sm text-zinc-300 leading-relaxed">{result.external_context}</p>
      </Section>
    </div>
  )
}

export function InitiativeReviewPage() {
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')

  const mut = useMutation({
    mutationFn: () => reviewInitiative(title.trim(), text.trim()),
  })

  const canSubmit = title.trim().length > 3 && text.trim().length > 20 && !mut.isPending

  return (
    <div className="flex h-full">
      {/* Левая панель — ввод */}
      <div className="w-96 shrink-0 border-r border-zinc-800 flex flex-col p-5 gap-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">Разбор инициативы</h2>
          <p className="text-xs text-zinc-500 mt-0.5">7-блочный анализ через корпус документов</p>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-zinc-400">Название</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: Запуск self-service кабинета для SMB"
            className="w-full text-sm bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
        </div>

        <div className="space-y-1 flex-1 flex flex-col">
          <label className="text-xs font-medium text-zinc-400">Текст инициативы</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Опиши суть инициативы: что делаем, зачем, какой ожидаемый результат, ресурсы..."
            className="flex-1 text-sm bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
        </div>

        <button
          onClick={() => mut.mutate()}
          disabled={!canSubmit}
          className={clsx(
            'w-full py-2.5 rounded-lg text-sm font-medium transition-colors',
            canSubmit
              ? 'bg-blue-600 text-white hover:bg-blue-500'
              : 'bg-zinc-800 text-zinc-600 cursor-not-allowed',
          )}
        >
          {mut.isPending ? 'Анализирую...' : 'Разобрать инициативу'}
        </button>

        {mut.isError && (
          <p className="text-xs text-red-400">Ошибка при анализе. Попробуй ещё раз.</p>
        )}
      </div>

      {/* Правая панель — результат */}
      <div className="flex-1 overflow-y-auto p-6">
        {!mut.data && !mut.isPending && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600 space-y-2">
            <p className="text-4xl">🔍</p>
            <p className="text-sm">Введи название и текст инициативы — получишь разбор по 7 блокам</p>
          </div>
        )}

        {mut.isPending && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-3">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            <p className="text-sm">Анализирую корпус документов...</p>
          </div>
        )}

        {mut.data && <ReviewResult result={mut.data} />}
      </div>
    </div>
  )
}
