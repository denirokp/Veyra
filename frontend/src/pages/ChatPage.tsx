import { useEffect, useRef, useState, type DragEvent } from 'react'
import clsx from 'clsx'
import { useChatStore } from '../store/chat'
import { ChatInput } from '../components/ChatInput'
import { ModePicker } from '../components/ModePicker'
import { AssistantMessage } from '../components/AssistantMessage'
import { DocumentUploadMessage } from '../components/DocumentUploadMessage'

export function ChatPage() {
  const { messages, loading, uploading, send, uploadFile, setPrefill, inputPrefill } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [draggingOver, setDraggingOver] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Page-wide drag-drop
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
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-zinc-950/80 border-2 border-dashed border-blue-500 rounded-none pointer-events-none">
          <div className="text-center space-y-2">
            <p className="text-4xl">📄</p>
            <p className="text-lg font-medium text-blue-300">Отпусти для загрузки в Хронику</p>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-3">
            <p className="text-3xl">📚</p>
            <p className="text-base font-medium text-zinc-400">Хроника</p>
            <p className="text-sm text-zinc-500">Спроси или перетащи документ для анализа</p>
            <div className="mt-4 space-y-2 text-xs text-zinc-600 text-center">
              <p>«Что мы знаем про агентский кабинет?»</p>
              <p>«Покажи расхождения по выручке»</p>
              <p>«Что обещали в стратегии 2025 и не сделали?»</p>
              <p>«Проверь инициативу: [текст]»</p>
            </div>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'system') {
            return (
              <div key={msg.id} className="flex justify-start">
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
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-2xl bg-blue-700 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
                  {msg.content}
                </div>
              </div>
            )
          }

          return (
            <div key={msg.id} className="flex justify-start">
              <div className="max-w-3xl bg-zinc-800 rounded-2xl rounded-tl-sm px-4 py-4 w-full">
                <AssistantMessage content={msg.content} response={msg.response} />
              </div>
            </div>
          )
        })}

        {(loading || (uploading && messages.at(-1)?.role !== 'system')) && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <span className={clsx('text-sm', uploading ? 'text-blue-400' : 'text-zinc-400', 'animate-pulse')}>
                {uploading ? 'Загружаю и анализирую документ…' : 'Ищу по документам…'}
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Mode picker + Input */}
      <ModePicker />
      <ChatInput
        onSend={send}
        onUpload={uploadFile}
        loading={loading}
        uploading={uploading}
        prefill={inputPrefill}
        onPrefillConsumed={() => setPrefill('')}
      />
    </div>
  )
}
