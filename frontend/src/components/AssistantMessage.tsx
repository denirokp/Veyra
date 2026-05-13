import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatResponse } from '../types'
import { SourceBadge } from './SourceBadge'

interface Props {
  content: string
  response?: ChatResponse
}

// Кастомизация рендера markdown под тёмную тему
const md = {
  h1: (p: any) => <h2 className="text-lg font-semibold text-zinc-100 mt-4 mb-2" {...p} />,
  h2: (p: any) => <h3 className="text-base font-semibold text-zinc-100 mt-3 mb-2" {...p} />,
  h3: (p: any) => <h4 className="text-sm font-semibold text-zinc-200 mt-2 mb-1" {...p} />,
  h4: (p: any) => <h5 className="text-sm font-semibold text-zinc-300 mt-2 mb-1" {...p} />,
  p:  (p: any) => <p className="text-zinc-100 leading-relaxed my-2" {...p} />,
  ul: (p: any) => <ul className="list-disc list-outside ml-5 my-2 space-y-1" {...p} />,
  ol: (p: any) => <ol className="list-decimal list-outside ml-5 my-2 space-y-1" {...p} />,
  li: (p: any) => <li className="text-zinc-100 leading-snug" {...p} />,
  strong: (p: any) => <strong className="text-zinc-50 font-semibold" {...p} />,
  em: (p: any) => <em className="text-zinc-200" {...p} />,
  code: (p: any) => <code className="bg-zinc-800 text-zinc-100 px-1 py-0.5 rounded text-xs" {...p} />,
  table: (p: any) => <table className="border-collapse text-xs my-2 w-full" {...p} />,
  th: (p: any) => <th className="border border-zinc-700 px-2 py-1 bg-zinc-800 text-left" {...p} />,
  td: (p: any) => <td className="border border-zinc-700 px-2 py-1 align-top" {...p} />,
  hr: (p: any) => <hr className="border-zinc-700 my-3" {...p} />,
  blockquote: (p: any) =>
    <blockquote className="border-l-2 border-zinc-600 pl-3 my-2 text-zinc-300" {...p} />,
}

export function AssistantMessage({ content, response }: Props) {
  if (!response) {
    return (
      <div className="text-zinc-200">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{content}</ReactMarkdown>
      </div>
    )
  }

  const { facts, hypotheses, warnings, requires_verification, metadata } = response

  return (
    <div className="space-y-4">
      {/* Прямой ответ — теперь поддерживает markdown (заголовки, списки, таблицы) */}
      <div className="text-zinc-100 leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>
          {response.answer}
        </ReactMarkdown>
      </div>

      {/* Факты */}
      {facts.length > 0 && (
        <section className="rounded-lg border border-blue-800/60 bg-blue-950/30 p-3 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-blue-400">
            Факты из документов
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
