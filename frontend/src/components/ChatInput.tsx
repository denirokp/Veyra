import { useRef, useState, type KeyboardEvent, type DragEvent } from 'react'
import clsx from 'clsx'
import type { ChatMode } from '../types'

const MODES: { value: ChatMode | null; label: string }[] = [
  { value: null, label: 'Авто' },
  { value: 'search', label: 'Поиск' },
  { value: 'contradictions', label: 'Расхождения' },
  { value: 'promises', label: 'Обещания' },
  { value: 'gaps', label: 'Серые зоны' },
  { value: 'write', label: 'Написать' },
  { value: 'validate', label: 'Оценить' },
]

interface Props {
  onSend: (text: string, file?: File) => void
  mode: ChatMode | null
  onModeChange: (mode: ChatMode | null) => void
  loading: boolean
}

export function ChatInput({ onSend, mode, onModeChange, loading }: Props) {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    onSend(trimmed, file ?? undefined)
    setText('')
    setFile(null)
  }

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  return (
    <div className="border-t border-zinc-700 bg-zinc-900 p-4 space-y-3">
      {/* Mode selector */}
      <div className="flex gap-2 flex-wrap">
        {MODES.map((m) => (
          <button
            key={String(m.value)}
            onClick={() => onModeChange(m.value)}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              mode === m.value
                ? 'bg-blue-600 text-white'
                : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600',
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* File drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={clsx(
          'relative flex items-start gap-3 rounded-xl border p-3 transition-colors',
          dragging ? 'border-blue-500 bg-blue-950/30' : 'border-zinc-700 bg-zinc-800',
        )}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Спроси что угодно... или перетащи файл сюда"
          rows={3}
          className="flex-1 resize-none bg-transparent text-zinc-100 placeholder-zinc-500 outline-none text-sm leading-relaxed"
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() || loading}
          className="self-end px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-blue-500 transition-colors"
        >
          {loading ? '...' : '↑ Отправить'}
        </button>
      </div>

      {/* Attached file */}
      {file && (
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <span>📎 {file.name}</span>
          <button onClick={() => setFile(null)} className="text-zinc-500 hover:text-zinc-300">✕</button>
        </div>
      )}
    </div>
  )
}
