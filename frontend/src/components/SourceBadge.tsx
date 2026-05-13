import type { SourceRef } from '../types'
import clsx from 'clsx'

const STATUS_COLOR: Record<string, string> = {
  actual:     'bg-emerald-50 text-emerald-800 border border-emerald-200',
  draft:      'bg-amber-50 text-amber-800 border border-amber-200',
  archived:   'bg-slate-100 text-slate-500 border border-slate-200',
  unknown:    'bg-slate-100 text-slate-500 border border-slate-200',
  superseded: 'bg-rose-50 text-rose-700 border border-rose-200',
}

export function SourceBadge({ source }: { source: SourceRef }) {
  const color = STATUS_COLOR[source.status] ?? STATUS_COLOR.unknown
  const titleEl = source.confluence_url ? (
    <a
      href={source.confluence_url}
      target="_blank"
      rel="noopener noreferrer"
      className="underline underline-offset-2 hover:text-sky-700"
    >
      {source.title}
    </a>
  ) : (
    <span>{source.title}</span>
  )

  return (
    <span className={clsx('inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-md', color)}>
      {titleEl}
      <span className="opacity-50">· L{source.hierarchy_level}</span>
      {source.section && <span className="opacity-50">› {source.section}</span>}
    </span>
  )
}
