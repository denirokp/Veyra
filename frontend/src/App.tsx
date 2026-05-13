import { useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queryClient'
import { ChatPage } from './pages/ChatPage'
import { TopBar } from './components/TopBar'
import { DocumentsDrawer } from './components/DocumentsDrawer'
import { useChatStore } from './store/chat'

function Inner() {
  const [documentsOpen, setDocumentsOpen] = useState(false)
  const { clear } = useChatStore()

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 font-sans">
      <TopBar
        onDocumentsOpen={() => setDocumentsOpen(true)}
        onClear={clear}
      />
      <main className="flex-1 overflow-hidden">
        <ChatPage />
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
