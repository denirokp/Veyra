import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { useChatStore } from '../store/chat'
import type { ChatMode } from '../types'

interface ModeOption {
  value: ChatMode | null
  label: string
  hint: string
}

const PRIMARY: ModeOption[] = [
  { value: null, label: 'Авто', hint: 'Режим определит модель сама по запросу' },
  { value: 'full', label: 'Полный разбор', hint: 'Все срезы сразу: факты, расхождения, серые зоны, рынок, гипотезы' },
  { value: 'search', label: 'Поиск', hint: 'Ответ по документам со ссылками на источники' },
  { value: 'write', label: 'Написать', hint: 'Подготовить черновик в стиле команды' },
  { value: 'validate', label: 'Инициатива', hint: 'Оценка инициативы или идеи' },
]

const SECONDARY: ModeOption[] = [
  { value: 'contradictions', label: 'Расхождения', hint: 'Численные и смысловые расхождения между документами' },
  { value: 'promises', label: 'Обещания', hint: 'Планы, дедлайны, что обещали и сделали' },
  { value: 'gaps', label: 'Серые зоны', hint: 'Что упущено, какие риски не закрыты' },
  { value: 'research', label: 'Рынок', hint: 'Конкуренты и внешний контекст' },
]

function Pill({ active, label, hint, onClick }: { active: boolean; label: string; hint: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      className={clsx(
        'px-3 py-1 rounded-full text-xs font-medium transition-colors border',
        active
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600',
      )}
    >
      {label}
    </button>
  )
}

export function ModePicker() {
  const mode = useChatStore((s) => s.mode)
  const setMode = useChatStore((s) => s.setMode)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const activeSecondary = SECONDARY.find((m) => m.value === mode)
  const moreActive = !!activeSecondary

  return (
    <div className="flex flex-wrap gap-1.5 px-4 pt-3 pb-1 border-t border-zinc-700 bg-zinc-900">
      {PRIMARY.map((m) => (
        <Pill
          key={m.label}
          active={mode === m.value}
          label={m.label}
          hint={m.hint}
          onClick={() => setMode(m.value)}
        />
      ))}

      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          title="Узкие срезы"
          className={clsx(
            'px-3 py-1 rounded-full text-xs font-medium transition-colors border flex items-center gap-1',
            moreActive
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600',
          )}
        >
          {moreActive ? `Ещё: ${activeSecondary!.label}` : 'Ещё'}
          <span className="text-[10px] opacity-70">▾</span>
        </button>

        {open && (
          <div className="absolute bottom-full left-0 mb-1 z-20 min-w-[200px] rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl py-1">
            {SECONDARY.map((m) => {
              const active = mode === m.value
              return (
                <button
                  key={m.label}
                  type="button"
                  onClick={() => {
                    setMode(m.value)
                    setOpen(false)
                  }}
                  title={m.hint}
                  className={clsx(
                    'w-full text-left px-3 py-1.5 text-xs transition-colors',
                    active ? 'text-blue-400 bg-zinc-800' : 'text-zinc-300 hover:bg-zinc-800',
                  )}
                >
                  <div className="font-medium">{m.label}</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">{m.hint}</div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
