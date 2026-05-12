import { useState } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { ChatPage } from './pages/ChatPage'
import { CorpusPage } from './pages/CorpusPage'
import { ContradictionsPage } from './pages/ContradictionsPage'
import { InitiativeReviewPage } from './pages/InitiativeReviewPage'
import { LogicSignalsPage } from './pages/LogicSignalsPage'
import { PromisesPage } from './pages/PromisesPage'
import { getCorpusStats } from './api/client'
import clsx from 'clsx'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })

type Tab = 'chat' | 'corpus' | 'initiative' | 'contradictions' | 'logic' | 'promises'

function NavItem({
  id,
  label,
  badge,
  current,
  onClick,
}: {
  id: Tab
  label: string
  badge?: number
  current: Tab
  onClick: (t: Tab) => void
}) {
  return (
    <button
      onClick={() => onClick(id)}
      className={clsx(
        'flex items-center justify-between w-full text-left px-3 py-2 rounded-lg text-sm transition-colors',
        current === id
          ? 'bg-blue-700/50 text-blue-200'
          : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200',
      )}
    >
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span className="text-xs bg-yellow-700/60 text-yellow-300 rounded-full px-1.5 py-0.5 leading-none">
          {badge}
        </span>
      )}
    </button>
  )
}

function Sidebar({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getCorpusStats,
    refetchInterval: 60_000,
  })

  return (
    <aside className="w-52 border-r border-zinc-800 bg-zinc-900 flex flex-col py-4 gap-1 px-2 shrink-0">
      <div className="px-3 pb-5">
        <div className="text-sm font-bold text-zinc-200 tracking-wide">Хроника</div>
        {stats && (
          <div className="mt-1 text-xs text-zinc-500">
            {stats.total_documents} документов
          </div>
        )}
      </div>

      <NavItem id="chat" label="💬 Чат" current={tab} onClick={setTab} />
      <NavItem id="corpus" label="📚 Корпус" current={tab} onClick={setTab} />
      <NavItem id="initiative" label="🚀 Инициативы" current={tab} onClick={setTab} />

      <div className="px-3 pt-3 pb-1 text-xs font-medium text-zinc-600 uppercase tracking-wider">
        Аналитика
      </div>
      <NavItem
        id="contradictions"
        label="⚡ Расхождения"
        badge={stats?.open_contradictions}
        current={tab}
        onClick={setTab}
      />
      <NavItem
        id="logic"
        label="🔍 Сигналы"
        badge={stats?.open_logic_signals}
        current={tab}
        onClick={setTab}
      />
      <NavItem
        id="promises"
        label="📋 Обещания"
        badge={stats?.open_promises}
        current={tab}
        onClick={setTab}
      />
    </aside>
  )
}

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')

  return (
    <QueryClientProvider client={qc}>
      <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans">
        <Sidebar tab={tab} setTab={setTab} />
        <main className="flex-1 overflow-hidden">
          {tab === 'chat' && <ChatPage />}
          {tab === 'corpus' && <CorpusPage />}
          {tab === 'initiative' && <InitiativeReviewPage />}
          {tab === 'contradictions' && <ContradictionsPage />}
          {tab === 'logic' && <LogicSignalsPage />}
          {tab === 'promises' && <PromisesPage />}
        </main>
      </div>
    </QueryClientProvider>
  )
}
