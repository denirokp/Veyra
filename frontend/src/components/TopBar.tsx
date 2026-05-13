import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { getDocsStats } from '../api/client'
import type { PageName } from '../App'

interface TopBarProps {
  page: PageName
  onPageChange: (p: PageName) => void
  onDocumentsOpen: () => void
  onClear: () => void
}

interface NavItem {
  id: PageName
  label: string
  icon?: string
  badgeKey?: 'open_contradictions' | 'open_logic_signals' | 'open_promises'
  badgeStyle?: 'alert' | 'muted'
}

const NAV: NavItem[] = [
  { id: 'chat', label: 'Чат', icon: '💬' },
  { id: 'documents', label: 'Документы', icon: '📂' },
  { id: 'contradictions', label: 'Расхождения', icon: '⚡', badgeKey: 'open_contradictions', badgeStyle: 'alert' },
  { id: 'signals', label: 'Сигналы', icon: '🔍', badgeKey: 'open_logic_signals', badgeStyle: 'alert' },
  { id: 'promises', label: 'Обещания', icon: '📋', badgeKey: 'open_promises', badgeStyle: 'muted' },
  { id: 'initiative', label: 'Инициативы', icon: '🚀' },
]

export function TopBar({ page, onPageChange, onDocumentsOpen, onClear }: TopBarProps) {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getDocsStats,
    refetchInterval: 60_000,
  })

  return (
    <header className="flex items-center justify-between px-5 py-2 border-b border-zinc-800 bg-zinc-900 shrink-0">
      <div className="flex items-center gap-1">
        <span className="text-sm font-bold text-zinc-100 tracking-wide mr-3">Хроника</span>

        {NAV.map((item) => {
          const active = page === item.id
          const badgeValue = item.badgeKey && stats ? (stats[item.badgeKey] ?? 0) : 0
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              className={clsx(
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors',
                active
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-700'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 border border-transparent',
              )}
            >
              {item.icon && <span>{item.icon}</span>}
              <span>{item.label}</span>
              {badgeValue > 0 && (
                <span
                  className={clsx(
                    'px-1.5 py-0 rounded text-[10px] font-semibold',
                    item.badgeStyle === 'alert'
                      ? 'bg-yellow-900/60 text-yellow-300'
                      : 'bg-zinc-800 text-zinc-400',
                  )}
                >
                  {badgeValue}
                </span>
              )}
            </button>
          )
        })}

        {stats && (
          <span className="text-xs text-zinc-600 ml-3">
            {stats.total_documents} док.
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onDocumentsOpen}
          className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors border border-zinc-700"
          title="Боковая панель управления документами"
        >
          📂 Файлы
        </button>
        {page === 'chat' && (
          <button
            onClick={onClear}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1.5"
          >
            Очистить чат
          </button>
        )}
      </div>
    </header>
  )
}
