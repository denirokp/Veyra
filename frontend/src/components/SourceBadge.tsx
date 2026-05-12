import type { SourceRef } from '../types'
import clsx from 'clsx'

const STATUS_COLOR: Record<string, string> = {
  actual: 'bg-emerald-900 text-emerald-200',
  draft: 'bg-yellow-900 text-yellow-200',
  archived: 'bg-yellow-900 text-yellow-200',
  unknown: 'bg-zinc-700 text-zinc-300',
  superseded: 'bg-red-900 text-red-300',
}

export function SourceBadge({ source }: { source: SourceRef }) {
  const color = STATUS_COLOR[source.status] ?? STATUS_COLOR.unknown
  const label = source.confluence_url ? (
    <a
      href={source.confluence_url}
      target="_blank"
      rel="noopener noreferrer"
      className="underline underline-offset-2"
    >
      {source.title}
    </a>
  ) : (
    <span>{source.title}</span>
  )

  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded', color)}>
      ↗ {label}
      <span className="opacity-60">· {source.status} · L{source.hierarchy_level}</span>
      {source.date && <span className="opacity-60">· {source.date}</span>}
    </span>
  )
}
