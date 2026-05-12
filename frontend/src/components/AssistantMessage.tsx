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
      <p className="text-zinc-100 leading-relaxed">{response.answer}</p>

      {/* Факты */}
      {facts.length > 0 && (
        <section className="rounded-lg border border-blue-800 bg-blue-950/40 p-3 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-blue-400">
            ━━━ ФАКТЫ ━━━
          </h4>
          <ul className="space-y-2">
            {facts.map((f, i) => (
              <li key={i} className="text-sm text-zinc-200">
                <span className="mr-1">•</span>
                {f.statement}
                <div className="mt-1">
                  <SourceBadge source={f.source} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Гипотезы */}
      {hypotheses.length > 0 && (
        <section className="rounded-lg border border-purple-800 bg-purple-950/40 p-3 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-purple-400">
            ━━━ ГИПОТЕЗЫ ━━━
          </h4>
          <ul className="space-y-1">
            {hypotheses.map((h, i) => (
              <li key={i} className="text-sm text-zinc-300">
                <span className="mr-1">•</span>
                {h}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Предупреждения */}
      {warnings.length > 0 && (
        <section className="rounded-lg border border-yellow-800 bg-yellow-950/40 p-3 space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-yellow-400">
            ━━━ ПРЕДУПРЕЖДЕНИЯ ━━━
          </h4>
          <ul className="space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-sm text-yellow-200">
                {w}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Требует проверки */}
      {requires_verification.length > 0 && (
        <section className="rounded-lg border border-zinc-600 bg-zinc-800/40 p-3 space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            ━━━ ТРЕБУЕТ ПРОВЕРКИ ━━━
          </h4>
          <ul className="space-y-1">
            {requires_verification.map((r, i) => (
              <li key={i} className="text-sm text-zinc-300">
                <span className="mr-1">•</span>
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Метаданные */}
      <div className="flex gap-3 text-xs text-zinc-500">
        <span>{metadata.latency_ms}ms</span>
        <span>{metadata.chunks_retrieved} chunks</span>
        <span>режим: {metadata.mode_detected}</span>
      </div>
    </div>
  )
}
