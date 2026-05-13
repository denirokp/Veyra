import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queryClient'
import { ChatPage } from './pages/ChatPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { ContradictionsPage } from './pages/ContradictionsPage'
import { LogicSignalsPage } from './pages/LogicSignalsPage'
import { PromisesPage } from './pages/PromisesPage'
import { InitiativeReviewPage } from './pages/InitiativeReviewPage'
import { TopBar } from './components/TopBar'
import { DocumentsDrawer } from './components/DocumentsDrawer'
import { useChatStore } from './store/chat'

export type PageName = 'chat' | 'documents' | 'contradictions' | 'signals' | 'promises' | 'initiative'

function PageContent({ page }: { page: PageName }) {
  switch (page) {
    case 'chat': return <ChatPage />
    case 'documents': return <DocumentsPage />
    case 'contradictions': return <ContradictionsPage />
    case 'signals': return <LogicSignalsPage />
    case 'promises': return <PromisesPage />
    case 'initiative': return <InitiativeReviewPage />
  }
}

function Inner() {
  const [page, setPage] = useState<PageName>('chat')
  const [documentsOpen, setDocumentsOpen] = useState(false)
  const { clear } = useChatStore()

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 font-sans">
      <TopBar
        page={page}
        onPageChange={setPage}
        onDocumentsOpen={() => setDocumentsOpen(true)}
        onClear={clear}
      />
      <main className="flex-1 overflow-hidden">
        <PageContent page={page} />
      </main>
      <DocumentsDrawer open={documentsOpen} onClose={() => setDocumentsOpen(false)} />
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
