import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listDocuments,
  uploadDocument,
  patchDocument,
  deleteDocument,
  getCorpusStats,
} from '../api/client'
import type { Document, DocumentStatus } from '../types'
import clsx from 'clsx'

const STATUS_COLOR: Record<DocumentStatus, string> = {
  actual: 'bg-emerald-900/60 text-emerald-300',
  draft: 'bg-yellow-900/60 text-yellow-300',
  archived: 'bg-zinc-700 text-zinc-300',
  superseded: 'bg-red-900/60 text-red-300',
  unknown: 'bg-zinc-700 text-zinc-400',
}

function DocRow({ doc }: { doc: Document }) {
  const qc = useQueryClient()
  const patch = useMutation({
    mutationFn: (p: Parameters<typeof patchDocument>[1]) => patchDocument(doc.id, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })
  const del = useMutation({
    mutationFn: () => deleteDocument(doc.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  return (
    <tr className="border-b border-zinc-700 hover:bg-zinc-800/50 transition-colors">
      <td className="px-4 py-3 text-sm text-zinc-100 max-w-xs truncate">{doc.title}</td>
      <td className="px-4 py-3">
        <span className={clsx('text-xs px-2 py-0.5 rounded', STATUS_COLOR[doc.status])}>
          {doc.status}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-zinc-400">L{doc.hierarchy_level}</td>
      <td className="px-4 py-3 text-xs text-zinc-400">{doc.type ?? '—'}</td>
      <td className="px-4 py-3 text-xs text-zinc-400">{doc.segment ?? '—'}</td>
      <td className="px-4 py-3 text-xs text-zinc-400">{doc.chunk_count ?? '...'}</td>
      <td className="px-4 py-3">
        <div className="flex gap-2 flex-wrap">
          <select
            value={doc.status}
            onChange={(e) => patch.mutate({ status: e.target.value })}
            className="text-xs bg-zinc-700 text-zinc-200 rounded px-2 py-1 border border-zinc-600"
          >
            {(['actual', 'draft', 'archived', 'superseded', 'unknown'] as DocumentStatus[]).map(
              (s) => <option key={s} value={s}>{s}</option>,
            )}
          </select>
          <button
            onClick={() => patch.mutate({ is_anchor: !doc.is_anchor })}
            className={clsx(
              'text-xs px-2 py-1 rounded border transition-colors',
              doc.is_anchor
                ? 'border-blue-500 text-blue-400 bg-blue-950/40'
                : 'border-zinc-600 text-zinc-400 hover:border-zinc-400',
            )}
            title="L1 якорный документ"
          >
            L1 {doc.is_anchor ? '✓' : ''}
          </button>
          <button
            onClick={() => del.mutate()}
            className="text-xs text-zinc-500 hover:text-red-400 px-2 py-1 rounded border border-zinc-700 hover:border-red-700 transition-colors"
          >
            ✕
          </button>
        </div>
      </td>
    </tr>
  )
}

function UploadZone() {
  const qc = useQueryClient()
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const upload = useCallback(async (file: File) => {
    setUploading(true)
    try {
      await uploadDocument(file, { title: file.name.replace(/\.[^.]+$/, '') })
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
    } finally {
      setUploading(false)
    }
  }, [qc])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) upload(f)
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      className={clsx(
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
        dragging ? 'border-blue-500 bg-blue-950/20' : 'border-zinc-600 hover:border-zinc-400',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.md,.txt,.html"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }}
      />
      <p className="text-zinc-400 text-sm">
        {uploading ? 'Загрузка и индексация...' : 'Перетащи документ или кликни · PDF, DOCX, MD, TXT'}
      </p>
    </div>
  )
}

export function CorpusPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const { data: docs = [] } = useQuery({
    queryKey: ['documents', statusFilter],
    queryFn: () => listDocuments(statusFilter ? { status: statusFilter } : undefined),
  })
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getCorpusStats,
  })

  return (
    <div className="flex flex-col h-full p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-100">Корпус документов</h2>
        {stats && (
          <div className="flex gap-4 text-xs text-zinc-400">
            <span>Всего: <strong className="text-zinc-200">{stats.total_documents}</strong></span>
            <span>Actual: <strong className="text-emerald-400">{stats.by_status.actual}</strong></span>
            <span>Расхождений: <strong className="text-yellow-400">{stats.open_contradictions}</strong></span>
            <span>Обещаний: <strong className="text-blue-400">{stats.open_promises}</strong></span>
          </div>
        )}
      </div>

      <UploadZone />

      {/* Filter */}
      <div className="flex gap-2">
        {['', 'actual', 'draft', 'archived', 'unknown'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600',
            )}
          >
            {s || 'Все'}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-zinc-700">
        <table className="w-full text-left">
          <thead className="bg-zinc-800 text-xs text-zinc-400 uppercase">
            <tr>
              <th className="px-4 py-3">Название</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Уровень</th>
              <th className="px-4 py-3">Тип</th>
              <th className="px-4 py-3">Сегмент</th>
              <th className="px-4 py-3">Чанков</th>
              <th className="px-4 py-3">Действия</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => <DocRow key={d.id} doc={d} />)}
          </tbody>
        </table>
        {docs.length === 0 && (
          <p className="text-center py-8 text-zinc-500 text-sm">Нет документов</p>
        )}
      </div>
    </div>
  )
}
