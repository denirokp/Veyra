import { useState } from 'react'
import type { Document, InitiativeReviewResult, InitiativeConflict, InitiativeAnchor } from '../types'
import clsx from 'clsx'

const VERDICT_CONFIG = {
  approve: { label: 'Всё ок', color: 'text-emerald-400', bg: 'bg-emerald-900/20 border-emerald-800' },
  needs_work: { label: 'Требует внимания', color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-800' },
  reject: { label: 'Противоречит стратегии', color: 'text-red-400', bg: 'bg-red-900/20 border-red-800' },
}

const SEVERITY_DOT: Record<string, string> = {
  high: 'bg-red-500',
  medium: 'bg-yellow-500',
  low: 'bg-zinc-500',
}

const ALIGN_ICON: Record<string, string> = {
  supports: '↑',
  neutral: '→',
  conflicts: '✗',
}

const ALIGN_COLOR: Record<string, string> = {
  supports: 'text-emerald-400',
  neutral: 'text-zinc-400',
  conflicts: 'text-red-400',
}

function ConflictItem({ c }: { c: InitiativeConflict }) {
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span className={clsx('mt-1.5 w-1.5 h-1.5 rounded-full shrink-0', SEVERITY_DOT[c.severity] ?? 'bg-zinc-500')} />
      <div className="space-y-0.5">
        <p className="text-xs text-zinc-200 leading-snug">{c.description}</p>
        {c.source && <p className="text-xs text-zinc-500">Источник: {c.source}</p>}
      </div>
    </div>
  )
}

function AnchorItem({ a }: { a: InitiativeAnchor }) {
  if (a.alignment === 'neutral') return null
  return (
    <div className="flex items-start gap-2 py-1">
      <span className={clsx('text-xs font-bold shrink-0 mt-0.5', ALIGN_COLOR[a.alignment])}>
        {ALIGN_ICON[a.alignment]}
      </span>
      <div>
        <span className="text-xs text-zinc-300 font-medium">{a.title}</span>
        <span className="text-xs text-zinc-500 ml-1">— {a.relevance.slice(0, 80)}{a.relevance.length > 80 ? '…' : ''}</span>
      </div>
    </div>
  )
}

interface Props {
  doc?: Document
  review?: InitiativeReviewResult
  text?: string
  onAsk: (prefix: string) => void
}

export function DocumentUploadMessage({ doc, review, text, onAsk }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (!doc) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/60 px-4 py-3 text-sm text-zinc-400">
        {text || 'Загрузка…'}
      </div>
    )
  }

  const verdict = review?.recommendation?.verdict
  const verdictCfg = verdict ? VERDICT_CONFIG[verdict] : null

  const conflicts = review?.conflicts ?? []
  const anchors = review?.strategic_anchors ?? []
  const conflictingAnchors = anchors.filter((a) => a.alignment === 'conflicts')
  const supportingAnchors = anchors.filter((a) => a.alignment === 'supports')
  const gaps = review?.gaps ?? []
  const summary = review?.summary ?? ''

  const hasIssues = conflicts.length > 0 || conflictingAnchors.length > 0

  return (
    <div className={clsx(
      'rounded-xl border border-dashed px-4 py-4 space-y-3 max-w-2xl',
      verdictCfg ? verdictCfg.bg : 'border-zinc-700 bg-zinc-900/60',
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-zinc-400">📄</span>
          <span className="text-sm font-semibold text-zinc-100">{doc.title}</span>
          <span className="text-xs text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">L{doc.hierarchy_level}</span>
          {verdictCfg && (
            <span className={clsx('text-xs font-semibold', verdictCfg.color)}>
              {verdictCfg.label}
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-600 shrink-0">добавлен в корпус</span>
      </div>

      {/* Summary */}
      {summary && (
        <p className="text-sm text-zinc-300 leading-snug">{summary}</p>
      )}

      {/* Conflicts — главное что нужно показать */}
      {conflicts.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-red-400 uppercase tracking-wide">
            ⚡ Сигналы к проверке ({conflicts.length})
          </p>
          <div className="border-l-2 border-red-900 pl-3">
            {(expanded ? conflicts : conflicts.slice(0, 2)).map((c, i) => (
              <ConflictItem key={i} c={c} />
            ))}
            {!expanded && conflicts.length > 2 && (
              <button
                onClick={() => setExpanded(true)}
                className="text-xs text-zinc-500 hover:text-zinc-300 py-1"
              >
                Ещё {conflicts.length - 2} сигнала…
              </button>
            )}
          </div>
        </div>
      )}

      {/* Conflicting anchors — с чем именно расходится */}
      {conflictingAnchors.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-orange-400 uppercase tracking-wide">
            Расходится с документами корпуса
          </p>
          <div className="space-y-0.5">
            {conflictingAnchors.map((a, i) => <AnchorItem key={i} a={a} />)}
          </div>
        </div>
      )}

      {/* Supporting anchors */}
      {supportingAnchors.length > 0 && !hasIssues && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-emerald-500 uppercase tracking-wide">
            Согласуется с
          </p>
          <div className="space-y-0.5">
            {supportingAnchors.slice(0, 3).map((a, i) => <AnchorItem key={i} a={a} />)}
          </div>
        </div>
      )}

      {/* Gaps */}
      {gaps.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {gaps.map((g, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
              Нет: {g.gap_type === 'owner' ? 'владельца' : g.gap_type === 'deadline' ? 'дедлайна' : g.gap_type === 'metric' ? 'метрик' : g.gap_type}
            </span>
          ))}
        </div>
      )}

      {/* No issues */}
      {!review && (
        <p className="text-xs text-zinc-500">
          Анализ запущен — результаты через ~30 сек.
        </p>
      )}
      {review && !hasIssues && gaps.length === 0 && (
        <p className="text-xs text-emerald-500">✓ Явных противоречий с корпусом не найдено</p>
      )}

      {/* Reasoning */}
      {review?.recommendation?.reasoning && (
        <p className="text-xs text-zinc-500 italic leading-snug border-t border-zinc-800 pt-2">
          {review.recommendation.reasoning}
        </p>
      )}

      {/* CTA */}
      <button
        onClick={() => onAsk(`По документу «${doc.title}»: `)}
        className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
      >
        Задать вопрос об этом документе →
      </button>
    </div>
  )
}
