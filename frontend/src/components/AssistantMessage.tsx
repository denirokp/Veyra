import type React from 'react'
import type { ChatResponse, SourceRef } from '../types'

// ---------- Section label ----------
function SectionLabel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`text-[10.5px] font-medium text-slate-500 uppercase tracking-[0.08em] ${className}`}>
      {children}
    </div>
  )
}

// ---------- Source chip (inline) ----------
function SourceChip({ source }: { source: SourceRef }) {
  const isAnchor = source.hierarchy_level === 1
  const isArchived = source.status === 'archived'

  if (source.confluence_url) {
    return (
      <a
        href={source.confluence_url}
        target="_blank"
        rel="noopener noreferrer"
        className={`inline-flex items-center gap-1 align-baseline text-[13px] leading-snug rounded ring-focus transition-colors duration-120 hover:underline underline-offset-2 ${
          isArchived
            ? 'text-slate-500 hover:text-slate-700'
            : 'text-sky-700 hover:text-sky-800'
        }`}
      >
        {isAnchor && (
          <svg xmlns="http://www.w3.org/2000/svg" width={11} height={11} viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            className="shrink-0 text-slate-700">
            <circle cx="12" cy="5" r="3"/><line x1="12" y1="22" x2="12" y2="8"/>
            <path d="M5 12H2a10 10 0 0 0 20 0h-3"/>
          </svg>
        )}
        <span className="font-medium whitespace-nowrap">{source.title}</span>
        {source.section && <span className="text-slate-400 font-normal"> › {source.section}</span>}
      </a>
    )
  }

  return (
    <span className={`inline-flex items-center gap-1 text-[13px] leading-snug ${
      isArchived ? 'text-slate-400' : 'text-sky-700'
    }`}>
      {isAnchor && (
        <svg xmlns="http://www.w3.org/2000/svg" width={11} height={11} viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
          className="shrink-0 text-slate-700">
          <circle cx="12" cy="5" r="3"/><line x1="12" y1="22" x2="12" y2="8"/>
          <path d="M5 12H2a10 10 0 0 0 20 0h-3"/>
        </svg>
      )}
      <span className="font-medium whitespace-nowrap">{source.title}</span>
      {source.section && <span className="text-slate-400 font-normal"> › {source.section}</span>}
    </span>
  )
}

// ---------- Sparkle bullet ----------
const SparkBullet = ({ tone = 'sky' }: { tone?: 'sky' | 'amber' | 'slate' | 'rose' }) => {
  const colors = { sky: 'text-sky-500', amber: 'text-amber-500', slate: 'text-slate-400', rose: 'text-rose-500' }
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
      className={`${colors[tone]} shrink-0 mt-[3px]`}>
      <path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>
      <path d="M5 3v4"/><path d="M3 5h4"/>
      <path d="M19 17v4"/><path d="M17 19h4"/>
    </svg>
  )
}

interface Props {
  content: string
  response?: ChatResponse
}

export function AssistantMessage({ content, response }: Props) {
  if (!response) {
    return (
      <article className="rounded-2xl border border-slate-200/80 bg-white shadow-soft overflow-hidden">
        <div className="px-5 sm:px-6 py-5">
          <p className="text-[14.5px] text-slate-900 leading-[1.6] whitespace-pre-wrap text-pretty">{content}</p>
        </div>
      </article>
    )
  }

  const { facts, hypotheses, warnings, requires_verification, metadata } = response
  const latencySec = metadata.latency_ms > 0 ? (metadata.latency_ms / 1000).toFixed(1) + ' сек' : null

  return (
    <article className="rounded-2xl border border-slate-200/80 bg-white shadow-soft overflow-hidden">
      <div className="px-5 sm:px-6 pt-5 pb-5">

        {/* Header */}
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-md bg-slate-900 flex items-center justify-center shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
              className="text-white">
              <path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>
              <path d="M5 3v4"/><path d="M3 5h4"/>
              <path d="M19 17v4"/><path d="M17 19h4"/>
            </svg>
          </div>
          <div className="text-[12.5px] text-slate-600 min-w-0">
            <span className="font-medium text-slate-900">Хроника</span>
            {metadata.chunks_retrieved > 0 && (
              <>
                <span className="text-slate-400 mx-1.5">·</span>
                <span>сверка с {metadata.chunks_retrieved} фрагментами</span>
              </>
            )}
          </div>
          {latencySec && (
            <div className="ml-auto text-[11px] text-slate-400 tabular-nums shrink-0">{latencySec}</div>
          )}
        </div>

        {/* Main answer text */}
        {response.answer && (
          <p className="text-[14.5px] text-slate-900 leading-[1.6] whitespace-pre-wrap text-pretty mb-5">
            {response.answer}
          </p>
        )}

        {/* Facts */}
        {facts.length > 0 && (
          <section className="mb-5">
            <SectionLabel className="mb-3">Факты</SectionLabel>
            <div className="space-y-3.5">
              {facts.map((f, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <SparkBullet tone="sky" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[14.5px] text-slate-900 leading-[1.6] text-pretty">{f.statement}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <SourceChip source={f.source} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <section className="mb-5">
            <SectionLabel className="mb-2.5">На что обратить внимание</SectionLabel>
            <div className="space-y-2">
              {warnings.map((w, i) => (
                <div key={i} className="rounded-xl border border-amber-200/70 bg-amber-50/40 px-4 py-3 flex items-start gap-2.5 shadow-soft">
                  <svg xmlns="http://www.w3.org/2000/svg" width={15} height={15} viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                    className="text-amber-600 mt-[2px] shrink-0">
                    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                  </svg>
                  <p className="text-[14px] leading-[1.6] text-amber-950 text-pretty">{w}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Hypotheses */}
        {hypotheses.length > 0 && (
          <section className="mb-5">
            <SectionLabel className="mb-3">Гипотезы</SectionLabel>
            <div className="space-y-3.5">
              {hypotheses.map((h, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <SparkBullet tone="amber" />
                  <p className="text-[14.5px] text-slate-900 leading-[1.6] text-pretty">{h}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Requires verification */}
        {requires_verification.length > 0 && (
          <section>
            <SectionLabel className="mb-2.5">Стоит проверить</SectionLabel>
            <ul className="space-y-2">
              {requires_verification.map((r, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[14px] text-slate-700 leading-[1.55]">
                  <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                    className="text-slate-400 mt-[4px] shrink-0">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                  </svg>
                  <span className="text-pretty">{r}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 sm:px-6 py-2.5 bg-slate-50/60 border-t border-slate-100 flex items-center justify-between text-[12px] text-slate-500">
        <div className="inline-flex items-center gap-3">
          <button type="button" className="hover:text-slate-900 ring-focus rounded transition-colors duration-120">
            Уточнить
          </button>
          <span className="text-slate-300">·</span>
          <span className="text-slate-400 tabular-nums">{metadata.mode_detected}</span>
        </div>
        <div className="inline-flex items-center gap-1 text-slate-400">
          <span className="mr-1">Полезно?</span>
          <button type="button"
            className="hover:text-emerald-700 hover:bg-emerald-50 rounded p-1 ring-focus transition-colors duration-120"
            aria-label="Полезно">
            <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 10v12"/>
              <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L14 2h1a2 2 0 0 1 2 2v1.88a3 3 0 0 1-2 2.88z"/>
            </svg>
          </button>
          <button type="button"
            className="hover:text-rose-700 hover:bg-rose-50 rounded p-1 ring-focus transition-colors duration-120"
            aria-label="Не полезно">
            <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 14V2"/>
              <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L10 22h-1a2 2 0 0 1-2-2v-1.88a3 3 0 0 1 2-2.88z"/>
            </svg>
          </button>
        </div>
      </div>
    </article>
  )
}
