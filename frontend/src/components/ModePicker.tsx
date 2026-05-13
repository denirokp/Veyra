import clsx from 'clsx'
import { useChatStore } from '../store/chat'
import type { ChatMode } from '../types'

interface ModeOption {
  value: ChatMode | null
  label: string
  hint: string
}

const MODES: ModeOption[] = [
  { value: null, label: 'Авто', hint: 'Режим определит модель сама по запросу' },
  { value: 'full', label: 'Полный разбор', hint: 'Все срезы сразу: факты, расхождения, серые зоны, рынок, гипотезы' },
  { value: 'search', label: 'Поиск', hint: 'Ответ по документам со ссылками на источники' },
  { value: 'contradictions', label: 'Расхождения', hint: 'Численные и смысловые расхождения между документами' },
  { value: 'promises', label: 'Обещания', hint: 'Планы, дедлайны, что обещали и сделали' },
  { value: 'gaps', label: 'Серые зоны', hint: 'Что упущено, какие риски не закрыты' },
  { value: 'research', label: 'Рынок', hint: 'Конкуренты и внешний контекст' },
  { value: 'write', label: 'Написать', hint: 'Подготовить черновик в стиле команды' },
  { value: 'validate', label: 'Инициатива', hint: 'Оценка инициативы или идеи' },
]

export function ModePicker() {
  const mode = useChatStore((s) => s.mode)
  const setMode = useChatStore((s) => s.setMode)

  return (
    <div className="flex flex-wrap gap-1.5 px-4 pt-3 pb-1 border-t border-zinc-700 bg-zinc-900">
      {MODES.map((m) => {
        const active = mode === m.value
        return (
          <button
            key={m.label}
            type="button"
            onClick={() => setMode(m.value)}
            title={m.hint}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors border',
              active
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600',
            )}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
