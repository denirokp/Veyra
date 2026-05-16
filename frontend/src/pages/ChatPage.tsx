import { useEffect, useRef, useState, type DragEvent } from 'react'
import { useChatStore } from '../store/chat'
import { ChatInput } from '../components/ChatInput'
import { AssistantMessage } from '../components/AssistantMessage'
import { DocumentUploadMessage } from '../components/DocumentUploadMessage'

// Streaming skeleton
function AssistantStreaming() {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white shadow-soft px-5 py-5 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-slate-900 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            className="text-white">
            <path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>
            <path d="M5 3v4"/><path d="M3 5h4"/>
            <path d="M19 17v4"/><path d="M17 19h4"/>
          </svg>
        </div>
        <div className="text-[12px] text-slate-500 inline-flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
            className="animate-spin">
            <line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/>
            <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>
            <line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>
            <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>
          </svg>
          <span>Сверяю с корпусом…</span>
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 rounded skel bg-slate-200 w-[88%]" />
        <div className="h-3 rounded skel bg-slate-200 w-[72%]" />
        <div className="h-3 rounded skel bg-slate-200 w-[80%]" />
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-3 space-y-2">
        <div className="h-2.5 rounded skel bg-slate-200 w-20" />
        <div className="h-3 rounded skel bg-slate-200 w-[92%]" />
        <div className="h-3 rounded skel bg-slate-200 w-[60%]" />
      </div>
    </div>
  )
}

// Empty state placeholder
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-16 px-6">
      <div className="w-12 h-12 rounded-2xl bg-slate-900 flex items-center justify-center mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" width={20} height={20} viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
          className="text-white">
          <path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>
          <path d="M5 3v4"/><path d="M3 5h4"/>
          <path d="M19 17v4"/><path d="M17 19h4"/>
        </svg>
      </div>
      <h2 className="text-[18px] font-semibold text-slate-900 tracking-tight mb-1">Хроника</h2>
      <p className="text-[14px] text-slate-500 mb-6 max-w-xs text-pretty">
        Задай вопрос по корпусу документов или перетащи файл для быстрой проверки
      </p>
      <div className="space-y-2 text-[13px] text-slate-400 text-left">
        {[
          '«Что решили про активацию XS-сегмента?»',
          '«Покажи расхождения по выручке»',
          '«Что обещали в стратегии и не сделали?»',
          '«Какие риски не закрыты в плане?»',
        ].map((hint, i) => (
          <div key={i} className="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
              className="text-slate-300 shrink-0">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
            <span>{hint}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ChatPage() {
  const { messages, loading, uploading, send, uploadFile, setPrefill, inputPrefill } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [draggingOver, setDraggingOver] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.types.includes('Files')) setDraggingOver(true)
  }
  const handleDragLeave = (e: DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDraggingOver(false)
  }
  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDraggingOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  return (
    <div
      className="flex flex-col h-full relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {draggingOver && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#f6f7f9]/80 border-2 border-dashed border-sky-400 rounded-none pointer-events-none">
          <div className="text-center space-y-3">
            <svg xmlns="http://www.w3.org/2000/svg" width={40} height={40} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
              className="text-sky-500 mx-auto">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <line x1="10" y1="9" x2="8" y2="9"/>
            </svg>
            <p className="text-[16px] font-medium text-slate-700">Отпусти для загрузки в Хронику</p>
          </div>
        </div>
      )}

      {/* Messages column */}
      <div className="flex-1 overflow-y-auto nice-scroll">
        <div className="max-w-[820px] mx-auto px-5 py-6">
          {messages.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-5">
              {messages.map((msg) => {
                if (msg.role === 'system') {
                  return (
                    <div key={msg.id}>
                      <DocumentUploadMessage
                        doc={msg.uploadedDoc}
                        review={msg.uploadReview}
                        text={msg.content}
                        onAsk={(prefix) => setPrefill(prefix)}
                      />
                    </div>
                  )
                }

                if (msg.role === 'user') {
                  return (
                    <div key={msg.id} className="flex items-start gap-3">
                      <div className="w-7 h-7 rounded-full bg-slate-900 text-white text-[11px] font-medium flex items-center justify-center shrink-0 tracking-tight">
                        АЛ
                      </div>
                      <div className="flex-1 min-w-0 pt-0.5">
                        <div className="text-[11px] text-slate-500 mb-1.5">
                          <span className="font-medium text-slate-700">Вы</span>
                          <span className="text-slate-300 mx-1.5">·</span>
                          <span>только что</span>
                        </div>
                        <p className="text-[15px] font-medium text-slate-900 leading-[1.45] text-pretty">
                          {msg.content}
                        </p>
                      </div>
                    </div>
                  )
                }

                // assistant
                return (
                  <div key={msg.id}>
                    <AssistantMessage content={msg.content} response={msg.response} />
                  </div>
                )
              })}

              {/* Loading skeleton */}
              {(loading || (uploading && messages.at(-1)?.role !== 'system')) && (
                <AssistantStreaming />
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-200 bg-[#f6f7f9] px-5 py-4">
        <div className="max-w-[820px] mx-auto">
          <ChatInput
            onSend={send}
            onUpload={uploadFile}
            loading={loading}
            uploading={uploading}
            prefill={inputPrefill}
            onPrefillConsumed={() => setPrefill('')}
          />
        </div>
      </div>
    </div>
  )
}
