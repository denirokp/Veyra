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
  role: 'user' | 'assistant' | 'system'
  content: string
  response?: ChatResponse
  uploadedDoc?: Document
  uploadReview?: InitiativeReviewResult
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
  open_logic_signals: number
  open_promises: number
}

export type InitiativeVerdict = 'approve' | 'needs_work' | 'reject'

export interface InitiativeAnchor {
  title: string
  relevance: string
  alignment: 'supports' | 'neutral' | 'conflicts'
}

export interface InitiativeConflict {
  description: string
  severity: 'high' | 'medium' | 'low'
  source?: string
}

export interface InitiativeGap {
  gap_type: 'metric' | 'owner' | 'deadline' | 'resource' | 'market_validation'
  description: string
}

export interface InitiativeAnalogue {
  title: string
  outcome: string
  lesson: string
}

export interface MarketContext {
  summary: string
  market_trends?: string[]
  competitors?: Array<{ name: string; approach: string }>
  benchmarks?: string[]
  risks?: string[]
  _disclaimer?: string
}

export interface MissingMetric {
  metric_name: string
  why_needed: string
  suggested_target?: string
  priority: 'must_have' | 'nice_to_have'
}

export interface InitiativeReviewResult {
  summary: string
  strategic_anchors: InitiativeAnchor[]
  conflicts: InitiativeConflict[]
  gaps: InitiativeGap[]
  analogues: InitiativeAnalogue[]
  external_context: string
  market_context?: MarketContext
  recommendation: { verdict: InitiativeVerdict; reasoning: string }
  metadata: {
    chunks_used: number
    doc_ids: string[]
    contradictions_found: number
    logic_signals_found: number
  }
}

export interface LogicSignal {
  id: string
  signal_type: 'strategic' | 'operational' | 'priority' | 'client'
  statement_a: string
  statement_b: string
  document_a: { id: string; title: string; hierarchy_level: number | null; created_at: string | null }
  document_b: { id: string; title: string; hierarchy_level: number | null; created_at: string | null }
  confidence: number
  status: 'open' | 'reviewed' | 'dismissed'
  review_notes: string | null
  created_at: string
}
