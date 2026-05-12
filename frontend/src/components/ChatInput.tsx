import { useRef, useState, type KeyboardEvent } from 'react'
import clsx from 'clsx'

const ACCEPTED = '.pdf,.docx,.md,.txt,.html'

interface Props {
  onSend: (text: string, file?: File) => void
  onUpload: (file: File) => void
  loading: boolean
  uploading: boolean
  prefill?: string
  onPrefillConsumed?: () => void
}

export function ChatInput({ onSend, onUpload, loading, uploading, prefill, onPrefillConsumed }: Props) {
  const [text, setText] = useState('')
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Consume prefill from parent (e.g. "Задать вопрос об этом документе")
  const currentText = prefill && text === '' ? prefill : text

  const handleTextChange = (val: string) => {
    setText(val)
    if (prefill && onPrefillConsumed) onPrefillConsumed()
  }

  const handleSend = () => {
    const trimmed = currentText.trim()
    if (loading || uploading) return
    if (!trimmed && !attachedFile) return

    if (attachedFile && !trimmed) {
      // File only → upload flow
      onUpload(attachedFile)
      setAttachedFile(null)
      return
    }

    onSend(trimmed, attachedFile ?? undefined)
    setText('')
    setAttachedFile(null)
    if (onPrefillConsumed) onPrefillConsumed()
  }

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (text.trim()) {
      // Text present → attach to message
      setAttachedFile(f)
    } else {
      // No text → direct upload
      onUpload(f)
    }
    e.target.value = ''
  }

  const busy = loading || uploading

  return (
    <div className="border-t border-zinc-700 bg-zinc-900 px-4 py-3">
      <div
        className={clsx(
          'flex items-end gap-2 rounded-xl border px-3 py-2 transition-colors',
          busy ? 'border-zinc-700 bg-zinc-800/50' : 'border-zinc-600 bg-zinc-800',
        )}
      >
        {/* Paperclip */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          title="Прикрепить документ"
          className="text-zinc-500 hover:text-zinc-300 transition-colors pb-1 shrink-0 disabled:opacity-40"
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={handleFileChange}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={currentText}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder={uploading ? 'Загружаю документ…' : 'Спроси или перетащи документ…'}
          disabled={busy}
          rows={1}
          style={{ resize: 'none', minHeight: '36px', maxHeight: '160px' }}
          className="flex-1 bg-transparent text-zinc-100 placeholder-zinc-500 outline-none text-sm leading-relaxed py-1 disabled:opacity-60"
          onInput={(e) => {
            const el = e.currentTarget
            el.style.height = 'auto'
            el.style.height = Math.min(el.scrollHeight, 160) + 'px'
          }}
        />

        {/* Send */}
        <button
          onClick={handleSend}
          disabled={(!currentText.trim() && !attachedFile) || busy}
          className="shrink-0 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-blue-500 transition-colors mb-0.5"
        >
          {uploading ? '⏳' : loading ? '…' : '↑'}
        </button>
      </div>

      {/* Attached file indicator */}
      {attachedFile && (
        <div className="flex items-center gap-2 mt-2 text-xs text-zinc-400">
          <span>📎 {attachedFile.name}</span>
          <button onClick={() => setAttachedFile(null)} className="text-zinc-500 hover:text-zinc-300">
            ✕
          </button>
        </div>
      )}
    </div>
  )
}
