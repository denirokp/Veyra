import { useEffect, useRef } from 'react'
import { useChatStore } from '../store/chat'
import { ChatInput } from '../components/ChatInput'
import { AssistantMessage } from '../components/AssistantMessage'

export function ChatPage() {
  const { messages, loading, mode, send, setMode, clear } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-zinc-700 bg-zinc-900">
        <h1 className="text-lg font-semibold text-zinc-100">Хроника</h1>
        <button
          onClick={clear}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Очистить диалог
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-2">
            <p className="text-2xl">📚</p>
            <p className="text-sm">Спроси что угодно о корпусе документов</p>
            <div className="text-xs text-zinc-600 space-y-1 mt-4">
              <p>«Что мы знаем про агентский кабинет?»</p>
              <p>«Какие цифры по L расходятся?»</p>
              <p>«Что обещали в стратегии 2025 и не сделали?»</p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'user' ? (
              <div className="max-w-2xl bg-blue-700 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
                {msg.content}
              </div>
            ) : (
              <div className="max-w-3xl bg-zinc-800 rounded-2xl rounded-tl-sm px-4 py-4 w-full">
                <AssistantMessage content={msg.content} response={msg.response} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <span className="text-zinc-400 text-sm animate-pulse">Анализирую корпус...</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput
        onSend={send}
        mode={mode}
        onModeChange={setMode}
        loading={loading}
      />
    </div>
  )
}
