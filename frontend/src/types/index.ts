export type DocumentStatus = 'actual' | 'draft' | 'archived' | 'superseded' | 'unknown'
export type ChatMode = 'search' | 'contradictions' | 'promises' | 'gaps' | 'write' | 'validate' | 'research'

export interface SourceRef {
  document_id: string
  title: string
  status: DocumentStatus
  hierarchy_level: number
  date?: string
  section?: string
  confluence_url?: string
}

export interface FactItem {
  statement: string
  source: SourceRef
}

export interface ChatResponse {
  answer: string
  facts: FactItem[]
  hypotheses: string[]
  warnings: string[]
  requires_verification: string[]
  metadata: {
    mode_detected: string
    agents_used: string[]
    latency_ms: number
    chunks_retrieved: number
  }
}

export interface ChatRequest {
  message: string
  mode?: ChatMode | null
  file?: string | null
  session_id?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: ChatResponse
  timestamp: Date
}

export interface Document {
  id: string
  title: string
  type: string
  status: DocumentStatus
  hierarchy_level: number
  segment?: string
  author?: string
  created_at?: string
  is_anchor: boolean
  is_style_anchor: boolean
  confluence_url?: string
  chunk_count?: number
  indexed_at?: string
}

export interface CorpusStats {
  total_documents: number
  by_status: Record<DocumentStatus, number>
  anchor_documents: number
  open_contradictions: number
  open_promises: number
}
