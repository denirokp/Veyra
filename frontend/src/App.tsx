import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPage } from './pages/ChatPage'
import { CorpusPage } from './pages/CorpusPage'
import clsx from 'clsx'

const qc = new QueryClient()

type Tab = 'chat' | 'corpus'

const TABS: { id: Tab; label: string }[] = [
  { id: 'chat', label: '💬 Чат' },
  { id: 'corpus', label: '📚 Корпус' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')

  return (
    <QueryClientProvider client={qc}>
      <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans">
        {/* Sidebar */}
        <aside className="w-48 border-r border-zinc-800 bg-zinc-900 flex flex-col py-4 gap-1 px-2">
          <div className="px-3 pb-4 text-sm font-bold text-zinc-300 tracking-wide">Хроника</div>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                'text-left px-3 py-2 rounded-lg text-sm transition-colors',
                tab === t.id
                  ? 'bg-blue-700/50 text-blue-200'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200',
              )}
            >
              {t.label}
            </button>
          ))}
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-hidden">
          {tab === 'chat' && <ChatPage />}
          {tab === 'corpus' && <CorpusPage />}
        </main>
      </div>
    </QueryClientProvider>
  )
}
