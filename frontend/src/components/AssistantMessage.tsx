import { useState } from 'react'
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

interface CollapsibleProps {
  title: string
  count: number
  colorClass: string  // основной цвет рамки/заголовка
  bgClass: string     // фоновый цвет
  textClass: string   // цвет заголовка
  collapseAfter?: number  // если count > этого числа, по умолчанию свёрнуто
  children: React.ReactNode
}

function Collapsible({
  title, count, colorClass, bgClass, textClass, collapseAfter = 5, children,
}: CollapsibleProps) {
  const [open, setOpen] = useState(count <= collapseAfter)
  return (
    <section className={`rounded-lg border ${colorClass} ${bgClass} p-3`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between text-xs font-semibold uppercase tracking-wider ${textClass} hover:opacity-80 transition-opacity`}
      >
        <span>{title} · {count}</span>
        <span className="opacity-60">{open ? '⌃ свернуть' : '⌄ показать'}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </section>
  )
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
      {/* Прямой ответ — markdown */}
      <div className="text-zinc-100 leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>
          {response.answer}
        </ReactMarkdown>
      </div>

      {/* Факты — сворачиваемые если их много */}
      {facts.length > 0 && (
        <Collapsible
          title="📎 Источники"
          count={facts.length}
          colorClass="border-blue-800/60"
          bgClass="bg-blue-950/30"
          textClass="text-blue-400"
          collapseAfter={5}
        >
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
        </Collapsible>
      )}

      {/* Предупреждения — обычно мало, но если много — свернём */}
      {warnings.length > 0 && (
        <Collapsible
          title="⚡ Расхождения и риски"
          count={warnings.length}
          colorClass="border-yellow-800/60"
          bgClass="bg-yellow-950/30"
          textClass="text-yellow-400"
          collapseAfter={4}
        >
          <ul className="space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-sm text-yellow-200 leading-snug">{w}</li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Гипотезы */}
      {hypotheses.length > 0 && (
        <Collapsible
          title="Гипотезы (вне документов)"
          count={hypotheses.length}
          colorClass="border-purple-800/60"
          bgClass="bg-purple-950/30"
          textClass="text-purple-400"
          collapseAfter={4}
        >
          <ul className="space-y-1">
            {hypotheses.map((h, i) => (
              <li key={i} className="text-sm text-zinc-300 leading-snug">
                <span className="text-purple-500 mr-1.5">•</span>
                {h}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Что стоит проверить */}
      {requires_verification.length > 0 && (
        <Collapsible
          title="🔍 Что стоит проверить"
          count={requires_verification.length}
          colorClass="border-orange-800/60"
          bgClass="bg-orange-950/30"
          textClass="text-orange-400"
          collapseAfter={4}
        >
          <ul className="space-y-1">
            {requires_verification.map((r, i) => (
              <li key={i} className="text-sm text-orange-200 leading-snug">
                <span className="mr-1.5">?</span>
                {r}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* Метаданные — что делалось под капотом + перформанс */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-600">
        {metadata.mode_detected && (
          <span className="text-zinc-500">mode: {metadata.mode_detected}</span>
        )}
        {(metadata as any).style && (
          <span>style: {(metadata as any).style}</span>
        )}
        <span>{metadata.chunks_retrieved} чанков</span>
        <span>{metadata.latency_ms}ms</span>
        {metadata.agents_used && metadata.agents_used.length > 1 && (
          <span title="LLM-агенты задействованные в обработке этого ответа">
            agents: {metadata.agents_used.join(' → ')}
          </span>
        )}
      </div>
    </div>
  )
}
