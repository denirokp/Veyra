import { useQuery } from '@tanstack/react-query'
import { getCorpusStats } from '../api/client'

interface TopBarProps {
  onCorpusOpen: () => void
  onClear: () => void
}

const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform)

export function TopBar({ onCorpusOpen, onClear }: TopBarProps) {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getCorpusStats,
    refetchInterval: 60_000,
  })

  const modKey = isMac() ? '⌘' : 'Ctrl'

  return (
    <header className="sticky top-0 z-10 bg-[#f6f7f9]/85 backdrop-blur border-b border-slate-200 shrink-0">
      <div className="max-w-[1280px] mx-auto px-6 h-[52px] flex items-center justify-between gap-6">

        {/* Left: brand + nav */}
        <div className="flex items-center gap-5 min-w-0">
          <div className="flex items-baseline gap-1.5 shrink-0">
            <span className="text-[16px] font-semibold text-slate-900 tracking-tight">Хроника</span>
            <span className="text-[10.5px] text-slate-400 font-mono">v2</span>
          </div>
          <nav className="hidden md:flex items-center gap-1 text-[13px] text-slate-500 shrink-0">
            <span className="font-medium text-slate-900 px-1">Чат</span>
            <span className="text-slate-300 mx-0.5">/</span>
            <button
              type="button"
              onClick={onCorpusOpen}
              className="hover:text-slate-900 rounded px-1 ring-focus transition-colors duration-120"
            >
              Корпус
            </button>
            <span className="text-slate-300 mx-0.5">/</span>
            <button
              type="button"
              className="hover:text-slate-900 rounded px-1 ring-focus transition-colors duration-120"
            >
              Обещания
            </button>
          </nav>
        </div>

        {/* Right: stats + actions */}
        <div className="flex items-center gap-4 shrink-0">
          {stats && (
            <div className="hidden lg:flex items-center gap-3 text-[12.5px] text-slate-600">
              <div className="inline-flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" width={13} height={13} viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                  className="text-slate-400">
                  <path d="M6 14l1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"/>
                </svg>
                <span className="tabular-nums font-medium text-slate-700">{stats.total_documents}</span>
                <span className="text-slate-500">в корпусе</span>
              </div>

              {stats.open_promises > 0 && (
                <>
                  <span className="text-slate-300">·</span>
                  <div className="inline-flex items-center gap-1.5">
                    <svg xmlns="http://www.w3.org/2000/svg" width={13} height={13} viewBox="0 0 24 24"
                      fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
                      className="text-amber-600">
                      <rect x="8" y="2" width="8" height="4" rx="1"/>
                      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                      <path d="M12 11h4"/><path d="M12 16h4"/>
                      <path d="M8 11h.01"/><path d="M8 16h.01"/>
                    </svg>
                    <span className="tabular-nums font-medium text-slate-700">{stats.open_promises}</span>
                    <span className="text-slate-500">просрочено</span>
                  </div>
                </>
              )}

              {(stats.open_contradictions > 0 || stats.open_logic_signals > 0) && (
                <>
                  <span className="text-slate-300">·</span>
                  <div className="inline-flex items-center gap-1.5 text-amber-700">
                    <span className="tabular-nums font-medium">
                      ⚡ {stats.open_contradictions + stats.open_logic_signals}
                    </span>
                    <span className="text-slate-500 text-[12px]">сигналов</span>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Cmd+K button */}
          <button
            type="button"
            className="inline-flex items-center gap-2 text-[12.5px] text-slate-500 bg-white border border-slate-200 hover:border-slate-300 hover:text-slate-700 rounded-lg pl-2.5 pr-1.5 py-1.5 shadow-soft ring-focus transition-colors duration-120"
            title={`Фокус на вводе (${modKey}K)`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={13} height={13} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <span className="hidden md:inline">Спросить</span>
            <kbd className="inline-flex items-center gap-0.5 text-[10px] font-mono text-slate-500">
              <span>{modKey}</span><span>K</span>
            </kbd>
          </button>

          {/* Corpus panel button */}
          <button
            type="button"
            onClick={onCorpusOpen}
            className="text-slate-500 hover:text-slate-900 ring-focus rounded p-1.5 transition-colors duration-120"
            title="Корпус документов"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <line x1="15" y1="3" x2="15" y2="21"/>
            </svg>
          </button>

          {/* Clear button */}
          <button
            type="button"
            onClick={onClear}
            className="text-[12.5px] text-slate-500 hover:text-slate-700 ring-focus rounded px-1 transition-colors duration-120"
          >
            Очистить
          </button>
        </div>
      </div>
    </header>
  )
}
