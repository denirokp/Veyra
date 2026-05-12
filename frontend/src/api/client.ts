import axios from 'axios'
import type { ChatRequest, ChatResponse, Document, CorpusStats, LogicSignal } from '../types'

const api = axios.create({ baseURL: '/api' })

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/chat', req)
  return data
}

export async function uploadDocument(
  file: File,
  meta: {
    title?: string
    status?: string
    is_anchor?: boolean
    segment?: string
    author?: string
    confluence_url?: string
  },
): Promise<Document> {
  const form = new FormData()
  form.append('file', file)
  if (meta.title) form.append('title', meta.title)
  if (meta.status) form.append('status', meta.status)
  if (meta.segment) form.append('segment', meta.segment)
  if (meta.author) form.append('author', meta.author)
  if (meta.confluence_url) form.append('confluence_url', meta.confluence_url)
  form.append('is_anchor', String(meta.is_anchor ?? false))
  const { data } = await api.post<Document>('/documents', form)
  return data
}

export async function listDocuments(params?: {
  status?: string
  segment?: string
}): Promise<Document[]> {
  const { data } = await api.get<Document[]>('/documents', { params })
  return data
}

export async function patchDocument(
  id: string,
  patch: { status?: string; is_anchor?: boolean; is_style_anchor?: boolean },
): Promise<Document> {
  const { data } = await api.patch<Document>(`/documents/${id}`, patch)
  return data
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/documents/${id}`)
}

export async function getCorpusStats(): Promise<CorpusStats> {
  const { data } = await api.get<CorpusStats>('/corpus/stats')
  return data
}

export async function getContradictions(status?: string) {
  const { data } = await api.get('/contradictions/numeric', { params: { status } })
  return data
}

export async function getLogicSignals(status?: string): Promise<LogicSignal[]> {
  const { data } = await api.get<LogicSignal[]>('/contradictions/logic', { params: { status } })
  return data
}

export async function updateLogicSignal(
  id: string,
  status: 'reviewed' | 'dismissed',
  review_notes?: string,
): Promise<void> {
  await api.patch(`/contradictions/logic/${id}`, null, {
    params: { status, review_notes },
  })
}

export async function getPromises(status?: string) {
  const { data } = await api.get('/promises', { params: { status } })
  return data
}

export async function getGaps() {
  const { data } = await api.get('/corpus/gaps')
  return data as Array<{ topic: string; reason: string; priority: 'high' | 'medium' | 'low' }>
}
