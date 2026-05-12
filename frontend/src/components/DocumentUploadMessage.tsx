import type { Document, InitiativeReviewResult } from '../types'
import clsx from 'clsx'

const VERDICT_CONFIG = {
  approve: { label: 'Одобрить', color: 'text-emerald-400' },
  needs_work: { label: 'Требует доработки', color: 'text-yellow-400' },
  reject: { label: 'Отклонить', color: 'text-red-400' },
}

interface Props {
  doc?: Document
  review?: InitiativeReviewResult
  text?: string
  onAsk: (prefix: string) => void
}

export function DocumentUploadMessage({ doc, review, text, onAsk }: Props) {
  // Error / loading text state
  if (!doc) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-400">
        {text || 'Загрузка…'}
      </div>
    )
  }

  const verdict = review?.recommendation?.verdict
  const verdictCfg = verdict ? VERDICT_CONFIG[verdict] : null
  const gaps = review?.gaps?.slice(0, 3) ?? []
  const signals = review?.metadata?.logic_signals_found ?? 0
  const contradictions = review?.metadata?.contradictions_found ?? 0

  return (
    <div className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/60 px-4 py-4 space-y-3 max-w-2xl">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-zinc-400">📄</span>
          <span className="text-sm font-medium text-zinc-200">{doc.title}</span>
          <span className="text-xs text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">
            L{doc.hierarchy_level}
          </span>
        </div>
        <span className="text-xs text-zinc-600 shrink-0">добавлен в корпус</span>
      </div>

      {review && (
        <>
          {verdictCfg && (
            <div className="flex items-center gap-2">
              <span className={clsx('text-sm font-semibold', verdictCfg.color)}>
                {verdictCfg.label}
              </span>
              <span className="text-xs text-zinc-500">·</span>
              <span className="text-xs text-zinc-400 leading-snug">
                {review.recommendation.reasoning.slice(0, 120)}
                {review.recommendation.reasoning.length > 120 ? '…' : ''}
              </span>
            </div>
          )}

          <div className="flex items-center gap-3 text-xs">
            {contradictions > 0 && (
              <span className="text-yellow-400">⚡ {contradictions} расх.</span>
            )}
            {signals > 0 && (
              <span className="text-yellow-400">🔍 {signals} сигн.</span>
            )}
            {gaps.length > 0 && (
              <span className="text-orange-400">
                🔍 Не хватает: {gaps.map((g) => g.gap_type).join(', ')}
              </span>
            )}
            {contradictions === 0 && signals === 0 && gaps.length === 0 && (
              <span className="text-emerald-500">✓ Конфликтов не обнаружено</span>
            )}
          </div>
        </>
      )}

      {!review && (
        <p className="text-xs text-zinc-500">
          Анализ запущен — сигналы и расхождения появятся в корпусе через ~30 сек.
        </p>
      )}

      <button
        onClick={() => onAsk(`По документу «${doc.title}»: `)}
        className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
      >
        Задать вопрос об этом документе →
      </button>
    </div>
  )
}
