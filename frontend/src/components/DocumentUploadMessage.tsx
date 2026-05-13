import { useState } from 'react'
import type React from 'react'
import type { Document, QuickReviewResult } from '../types'

const VERDICT_LABEL: Record<string, string> = {
  approve:    'Готово к согласованию',
  needs_work: 'Требует доработки',
  reject:     'Серьёзные расхождения',
}

const VERDICT_DOT_SEV: Record<string, 'high' | 'medium' | 'low'> = {
  reject:     'high',
  needs_work: 'medium',
  approve:    'low',
}

const VERDICT_COLOR: Record<string, string> = {
  approve:    'bg-emerald-600',
  needs_work: 'bg-amber-600',
  reject:     'bg-rose-600',
}

const VERDICT_TEXT: Record<string, string> = {
  approve:    'text-emerald-700',
  needs_work: 'text-amber-700',
  reject:     'text-rose-700',
}

// Severity dot sizes
const SEV_DOT: Record<string, string> = {
  high:   'bg-rose-600',
  medium: 'bg-amber-600',
  low:    'bg-slate-400',
}

function SeverityDot({ sev }: { sev: 'high' | 'medium' | 'low' }) {
  return <span className={`inline-block rounded-full w-[6px] h-[6px] ${SEV_DOT[sev]} shrink-0`} />
}

// ---------- Expandable row ----------
function ExpandRow({
  open,
  onToggle,
  icon,
  label,
  tone = 'slate',
  children,
}: {
  open: boolean
  onToggle: () => void
  icon: React.ReactNode
  label: string
  tone?: 'emerald' | 'amber' | 'slate'
  children: React.ReactNode
}) {
  const tones = {
    emerald: open ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200 bg-white hover:border-emerald-200',
    amber:   open ? 'border-amber-200 bg-amber-50/40'     : 'border-slate-200 bg-white hover:border-amber-200',
    slate:   open ? 'border-slate-300 bg-slate-50/60'     : 'border-slate-200 bg-white hover:border-slate-300',
  }
  return (
    <div className={`rounded-xl border ${tones[tone]} transition-colors duration-120`}>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left ring-focus rounded-xl"
        aria-expanded={open}
      >
        {icon}
        <span className="text-[13.5px] font-medium text-slate-800 flex-1 truncate">{label}</span>
        <svg xmlns="http://www.w3.org/2000/svg" width={15} height={15} viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
          className={`text-slate-400 transition-transform duration-120 shrink-0 ${open ? 'rotate-90' : ''}`}>
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      {open && <div className="px-3.5 pb-3.5">{children}</div>}
    </div>
  )
}

interface Props {
  doc?: Document
  review?: QuickReviewResult
  text?: string
  onAsk: (prefix: string) => void
}

export function DocumentUploadMessage({ doc, review, text, onAsk }: Props) {
  const [openConflicts, setOpenConflicts] = useState(true)
  const [openGaps, setOpenGaps] = useState(false)

  // Loading / error state
  if (!doc) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-3 text-[13.5px] text-slate-500 shadow-soft">
        {text || 'Загрузка…'}
      </div>
    )
  }

  const verdict = review?.verdict ?? 'needs_work'
  const verdictSev = VERDICT_DOT_SEV[verdict]
  const conflicts = review?.conflicts ?? []
  const gaps = review?.gaps ?? []
  const summary = review?.summary ?? ''

  return (
    <div className="relative rounded-2xl border border-slate-200/80 bg-white shadow-soft overflow-hidden max-w-2xl w-full">
      {/* Verdict color bar */}
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${VERDICT_COLOR[verdict]}`} aria-hidden="true" />

      <div className="pl-5 pr-5 sm:pl-6 sm:pr-6 py-5">
        {/* Header */}
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 shrink-0 rounded-lg bg-sky-50 border border-sky-100 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width={18} height={18} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
              className="text-sky-700">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <line x1="10" y1="9" x2="8" y2="9"/>
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="text-[10.5px] font-mono text-slate-500 uppercase tracking-wider">Quick Check</span>
              <span className="text-slate-300">·</span>
              <span className="text-[11.5px] text-slate-500">только что</span>
            </div>
            <div className="text-[18px] font-semibold text-slate-900 tracking-tight leading-tight">{doc.title}</div>
            <div className="text-[13px] mt-1.5 flex items-center gap-2">
              <SeverityDot sev={verdictSev} />
              <span className={`font-medium ${VERDICT_TEXT[verdict]}`}>
                {VERDICT_LABEL[verdict]}
              </span>
              {!review && (
                <span className="text-slate-400 text-[12px]">— анализ запущен…</span>
              )}
            </div>
          </div>
        </div>

        {/* Summary */}
        {summary && (
          <div className="mb-5 pl-[52px]">
            <p className="text-[14.5px] text-slate-700 leading-[1.6] text-pretty">{summary}</p>
          </div>
        )}

        {/* Expand rows */}
        <div className="space-y-2 pl-[52px]">
          {conflicts.length > 0 && (
            <ExpandRow
              open={openConflicts}
              onToggle={() => setOpenConflicts((v) => !v)}
              tone="amber"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                  className="text-amber-600 shrink-0">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              }
              label={`Потенциальные конфликты (${conflicts.length})`}
            >
              <ul className="mt-2.5 space-y-2">
                {conflicts.map((c, i) => (
                  <li key={i} className="rounded-lg border border-slate-200 bg-slate-50/60 px-3.5 py-3 text-[13.5px] text-slate-700 leading-[1.6]">
                    {c}
                  </li>
                ))}
              </ul>
            </ExpandRow>
          )}

          {gaps.length > 0 && (
            <ExpandRow
              open={openGaps}
              onToggle={() => setOpenGaps((v) => !v)}
              tone="slate"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                  className="text-slate-500 shrink-0">
                  <path d="M10.1 2.18a9.93 9.93 0 0 1 3.8 0"/>
                  <path d="M17.6 3.71a9.95 9.95 0 0 1 2.69 2.7"/>
                  <path d="M21.82 10.1a9.93 9.93 0 0 1 0 3.8"/>
                  <path d="M20.29 17.6a9.95 9.95 0 0 1-2.7 2.69"/>
                  <path d="M13.9 21.82a9.94 9.94 0 0 1-3.8 0"/>
                  <path d="M6.4 20.29a9.95 9.95 0 0 1-2.69-2.7"/>
                  <path d="M2.18 13.9a9.93 9.93 0 0 1 0-3.8"/>
                  <path d="M3.71 6.4a9.95 9.95 0 0 1 2.7-2.69"/>
                </svg>
              }
              label={`Не хватает: ${gaps.slice(0, 2).join(', ')}${gaps.length > 2 ? '…' : ''}`}
            >
              <ul className="mt-2.5 space-y-2">
                {gaps.map((g, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[13.5px] text-slate-700">
                    <svg xmlns="http://www.w3.org/2000/svg" width={13} height={13} viewBox="0 0 24 24"
                      fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                      className="text-slate-400 mt-[3px] shrink-0">
                      <path d="M10.1 2.18a9.93 9.93 0 0 1 3.8 0"/>
                      <path d="M17.6 3.71a9.95 9.95 0 0 1 2.69 2.7"/>
                      <path d="M21.82 10.1a9.93 9.93 0 0 1 0 3.8"/>
                      <path d="M20.29 17.6a9.95 9.95 0 0 1-2.7 2.69"/>
                      <path d="M13.9 21.82a9.94 9.94 0 0 1-3.8 0"/>
                      <path d="M6.4 20.29a9.95 9.95 0 0 1-2.69-2.7"/>
                      <path d="M2.18 13.9a9.93 9.93 0 0 1 0-3.8"/>
                      <path d="M3.71 6.4a9.95 9.95 0 0 1 2.7-2.69"/>
                    </svg>
                    <span>{g}</span>
                  </li>
                ))}
              </ul>
            </ExpandRow>
          )}

          {review && conflicts.length === 0 && gaps.length === 0 && (
            <div className="flex items-center gap-2 text-[13.5px] text-emerald-700 px-1">
              <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
                className="text-emerald-600 shrink-0">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              Явных противоречий с корпусом не найдено
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-5 pt-4 border-t border-slate-100 flex items-center gap-2 flex-wrap pl-[52px]">
          <button
            type="button"
            onClick={() => onAsk(`По документу «${doc.title}»: `)}
            className="inline-flex items-center gap-1.5 font-medium rounded-md transition-colors duration-120 active:scale-[0.98] ring-focus px-3 py-1.5 text-[13px] bg-white text-slate-800 hover:bg-slate-50 border border-slate-200"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
              className="text-slate-500">
              <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/>
              <path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3z"/>
            </svg>
            Задать вопрос по документу
          </button>
          <span className="text-[11.5px] text-slate-400 ml-auto">
            добавлен в корпус
          </span>
        </div>
      </div>
    </div>
  )
}
