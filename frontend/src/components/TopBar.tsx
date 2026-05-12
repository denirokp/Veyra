import { useQuery } from '@tanstack/react-query'
import { getCorpusStats } from '../api/client'
import clsx from 'clsx'

interface TopBarProps {
  onCorpusOpen: () => void
  onClear: () => void
}

export function TopBar({ onCorpusOpen, onClear }: TopBarProps) {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getCorpusStats,
    refetchInterval: 60_000,
  })

  const hasAlerts = (stats?.open_contradictions ?? 0) + (stats?.open_logic_signals ?? 0) > 0

  return (
    <header className="flex items-center justify-between px-5 py-2.5 border-b border-zinc-800 bg-zinc-900 shrink-0">
      <div className="flex items-center gap-4">
        <span className="text-sm font-bold text-zinc-100 tracking-wide">Хроника</span>

        {stats && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-zinc-500">{stats.total_documents} документов</span>

            {stats.open_contradictions > 0 && (
              <span className={clsx('px-1.5 py-0.5 rounded', hasAlerts ? 'bg-yellow-900/60 text-yellow-300' : 'text-zinc-600')}>
                ⚡ {stats.open_contradictions}
              </span>
            )}

            {stats.open_logic_signals > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-yellow-900/60 text-yellow-300">
                🔍 {stats.open_logic_signals}
              </span>
            )}

            {stats.open_promises > 0 && (
              <span className="text-zinc-500">📋 {stats.open_promises}</span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onCorpusOpen}
          className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors border border-zinc-700"
        >
          📂 Корпус
        </button>
        <button
          onClick={onClear}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1.5"
        >
          Очистить
        </button>
      </div>
    </header>
  )
}
