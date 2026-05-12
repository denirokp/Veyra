import type { ChatResponse } from '../types'
import { SourceBadge } from './SourceBadge'

interface Props {
  content: string
  response?: ChatResponse
}

export function AssistantMessage({ content, response }: Props) {
  if (!response) {
    return <p className="text-zinc-200 whitespace-pre-wrap">{content}</p>
  }

  const { facts, hypotheses, warnings, requires_verification, metadata } = response

  return (
    <div className="space-y-4">
      {/* Прямой ответ */}
      <p className="text-zinc-100 leading-relaxed whitespace-pre-wrap">{response.answer}</p>

      {/* Факты */}
      {facts.length > 0 && (
        <section className="rounded-lg border border-blue-800/60 bg-blue-950/30 p-3 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-blue-400">
            Факты из корпуса
          </h4>
          <ul className="space-y-2.5">
            {facts.map((f, i) => (
              <li key={i} className="text-sm text-zinc-200 leading-snug">
                <span className="text-blue-500 mr-1.5">•</span>
                {f.statement}
                <div className="mt-1 ml-3">
                  <SourceBadge source={f.source} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Предупреждения — показываем раньше гипотез, они важнее */}
      {warnings.length > 0 && (
        <section className="rounded-lg border border-yellow-800/60 bg-yellow-950/30 p-3 space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-yellow-400">
            ⚡ Расхождения и риски
          </h4>
          <ul className="space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-sm text-yellow-200 leading-snug">
                {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Гипотезы */}
      {hypotheses.length > 0 && (
        <section className="rounded-lg border border-purple-800/60 bg-purple-950/30 p-3 space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-purple-400">
            Гипотезы (нет в документах)
          </h4>
          <ul className="space-y-1">
            {hypotheses.map((h, i) => (
              <li key={i} className="text-sm text-zinc-300 leading-snug">
                <span className="text-purple-500 mr-1.5">•</span>
                {h}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Требует проверки — теперь это "что не учтено" */}
      {requires_verification.length > 0 && (
        <section className="rounded-lg border border-orange-800/60 bg-orange-950/30 p-3 space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-orange-400">
            🔍 Что стоит проверить
          </h4>
          <ul className="space-y-1">
            {requires_verification.map((r, i) => (
              <li key={i} className="text-sm text-orange-200 leading-snug">
                <span className="mr-1.5">?</span>
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Метаданные — минимально */}
      <div className="flex gap-3 text-xs text-zinc-600">
        <span>{metadata.chunks_retrieved} источников</span>
        <span>{metadata.latency_ms}ms</span>
      </div>
    </div>
  )
}
