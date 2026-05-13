import { useRef, useState, useEffect, type KeyboardEvent, type RefObject } from 'react'

const ACCEPTED = '.pdf,.docx,.md,.txt,.html'

const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform)

interface AttachedFileInfo {
  filename: string
  size: string
}

interface Props {
  onSend: (text: string, file?: File) => void
  onUpload: (file: File) => void
  loading: boolean
  uploading: boolean
  prefill?: string
  onPrefillConsumed?: () => void
  inputRef?: RefObject<HTMLTextAreaElement>
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

export function ChatInput({ onSend, onUpload, loading, uploading, prefill, onPrefillConsumed, inputRef }: Props) {
  const [text, setText] = useState('')
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const internalRef = useRef<HTMLTextAreaElement>(null)
  const ta = inputRef ?? internalRef

  const currentText = prefill && text === '' ? prefill : text

  // Auto-resize textarea
  useEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
  }, [currentText, ta])

  // Cmd+K focus
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        ta.current?.focus()
      }
    }
    window.addEventListener('keydown', handler as any)
    return () => window.removeEventListener('keydown', handler as any)
  }, [ta])

  const handleTextChange = (val: string) => {
    setText(val)
    if (prefill && onPrefillConsumed) onPrefillConsumed()
  }

  const handleSend = () => {
    const trimmed = currentText.trim()
    if (loading || uploading) return
    if (!trimmed && !attachedFile) return

    if (attachedFile && !trimmed) {
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
    if (currentText.trim()) {
      setAttachedFile(f)
    } else {
      onUpload(f)
    }
    e.target.value = ''
  }

  const busy = loading || uploading
  const canSend = (currentText.trim() || attachedFile) && !busy
  const modKey = isMac() ? '⌘' : 'Ctrl'

  const fileInfo: AttachedFileInfo | null = attachedFile
    ? { filename: attachedFile.name, size: formatBytes(attachedFile.size) }
    : null

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-soft-h focus-within:border-slate-400 transition-colors duration-120">

      {/* Attached file chip */}
      {fileInfo && (
        <div className="px-4 pt-3 pb-2 border-b border-slate-100 flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-2 bg-sky-50 border border-sky-100 rounded-lg px-2.5 py-1.5 text-[12.5px] text-sky-800">
            <svg xmlns="http://www.w3.org/2000/svg" width={13} height={13} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
              className="text-sky-600">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <line x1="10" y1="9" x2="8" y2="9"/>
            </svg>
            <span className="font-medium">{fileInfo.filename}</span>
            <span className="text-sky-600/70">· {fileInfo.size}</span>
            <button
              type="button"
              onClick={() => setAttachedFile(null)}
              className="text-sky-500 hover:text-sky-800 ring-focus rounded ml-1 transition-colors duration-120"
              aria-label="Убрать файл"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width={12} height={12} viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </span>
          <span className="text-[11.5px] text-slate-500">При отправке запустится Quick Check</span>
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-1 px-3 py-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          title="Прикрепить документ"
          className="text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-md p-1.5 ring-focus transition-colors duration-120 disabled:opacity-40 shrink-0"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={handleFileChange}
        />

        <textarea
          ref={ta}
          rows={1}
          placeholder={uploading ? 'Загружаю документ…' : 'Спросить или загрузить документ на разбор…'}
          value={currentText}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={handleKey}
          disabled={busy}
          className="flex-1 resize-none bg-transparent text-[14.5px] leading-[1.55] text-slate-900 placeholder:text-slate-400 px-1.5 py-1.5 max-h-40 outline-none disabled:opacity-60"
          style={{ minHeight: '36px' }}
        />

        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="inline-flex items-center gap-1.5 font-medium rounded-md transition-colors duration-120 active:scale-[0.98] ring-focus disabled:opacity-50 disabled:pointer-events-none px-3 py-1.5 text-[13px] bg-slate-900 text-white hover:bg-slate-700 border border-slate-900 shrink-0"
        >
          {uploading ? 'Загружаю…' : loading ? 'Думаю…' : attachedFile ? 'Разобрать' : 'Отправить'}
          {!loading && !uploading && (
            <svg xmlns="http://www.w3.org/2000/svg" width={14} height={14} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          )}
        </button>
      </div>

      {/* Keyboard hints */}
      <div className="px-4 pb-2.5 pt-0.5 flex items-center justify-between text-[11px] text-slate-400">
        <div className="flex items-center gap-2">
          <span>Отправить</span>
          <kbd className="inline-flex items-center min-w-[18px] px-1.5 py-[2px] rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">↵</kbd>
          <span>·</span>
          <span>Перенос</span>
          <kbd className="inline-flex items-center min-w-[18px] px-1.5 py-[2px] rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">⇧</kbd>
          <kbd className="inline-flex items-center min-w-[18px] px-1.5 py-[2px] rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">↵</kbd>
        </div>
        <div className="flex items-center gap-1">
          <span>Фокус</span>
          <kbd className="inline-flex items-center min-w-[18px] px-1.5 py-[2px] rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">{modKey}</kbd>
          <kbd className="inline-flex items-center min-w-[18px] px-1.5 py-[2px] rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">K</kbd>
        </div>
      </div>
    </div>
  )
}
