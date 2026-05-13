import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queryClient'
import { ChatPage } from './pages/ChatPage'
import { TopBar } from './components/TopBar'
import { CorpusDrawer } from './components/CorpusDrawer'
import { useChatStore } from './store/chat'

function Inner() {
  const [corpusOpen, setCorpusOpen] = useState(false)
  const { clear } = useChatStore()

  return (
    <div className="flex flex-col h-screen bg-[#f6f7f9] text-slate-900 font-sans">
      <TopBar
        onCorpusOpen={() => setCorpusOpen(true)}
        onClear={clear}
      />
      <main className="flex-1 overflow-hidden">
        <ChatPage />
      </main>
      <CorpusDrawer open={corpusOpen} onClose={() => setCorpusOpen(false)} />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Inner />
    </QueryClientProvider>
  )
}
