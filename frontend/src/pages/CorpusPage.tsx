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
  actual:     'bg-emerald-50 text-emerald-800 border border-emerald-200',
  draft:      'bg-amber-50 text-amber-800 border border-amber-200',
  archived:   'bg-slate-100 text-slate-500 border border-slate-200',
  superseded: 'bg-rose-50 text-rose-700 border border-rose-200',
  unknown:    'bg-slate-100 text-slate-500 border border-slate-200',
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
    <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="px-4 py-3 text-[13.5px] text-slate-900 max-w-xs truncate font-medium">{doc.title}</td>
      <td className="px-4 py-3">
        <span className={clsx('text-[11.5px] px-2 py-0.5 rounded-md', STATUS_COLOR[doc.status])}>
          {doc.status}
        </span>
      </td>
      <td className="px-4 py-3 text-[12px] text-slate-500 font-mono">L{doc.hierarchy_level}</td>
      <td className="px-4 py-3 text-[12px] text-slate-500">{doc.type ?? '—'}</td>
      <td className="px-4 py-3 text-[12px] text-slate-500">{doc.segment ?? '—'}</td>
      <td className="px-4 py-3 text-[12px] text-slate-500 tabular-nums">{doc.chunk_count ?? '...'}</td>
      <td className="px-4 py-3">
        <div className="flex gap-2 flex-wrap">
          <select
            value={doc.status}
            onChange={(e) => patch.mutate({ status: e.target.value })}
            className="text-[12px] bg-white text-slate-700 rounded-md px-2 py-1 border border-slate-200 focus:outline-none focus:border-slate-400"
          >
            {(['actual', 'draft', 'archived', 'superseded', 'unknown'] as DocumentStatus[]).map(
              (s) => <option key={s} value={s}>{s}</option>,
            )}
          </select>
          <button
            onClick={() => patch.mutate({ is_anchor: !doc.is_anchor })}
            className={clsx(
              'text-[12px] px-2 py-1 rounded-md border transition-colors duration-120',
              doc.is_anchor
                ? 'border-slate-800 text-slate-900 bg-slate-100'
                : 'border-slate-200 text-slate-500 hover:border-slate-400',
            )}
            title="L1 якорный документ"
          >
            Якорь{doc.is_anchor ? ' ✓' : ''}
          </button>
          <button
            onClick={() => del.mutate()}
            className="text-[12px] text-slate-400 hover:text-rose-600 px-2 py-1 rounded-md border border-slate-200 hover:border-rose-300 transition-colors duration-120"
          >
            Удалить
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
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors duration-120',
        dragging
          ? 'border-sky-400 bg-sky-50'
          : 'border-slate-200 hover:border-slate-300 bg-white',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.md,.txt,.html"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }}
      />
      <div className="flex flex-col items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
          className={clsx('mb-1', dragging ? 'text-sky-500' : 'text-slate-400')}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <p className="text-[13.5px] text-slate-600">
          {uploading
            ? 'Загрузка и индексация…'
            : 'Перетащи документ или кликни для выбора'}
        </p>
        <p className="text-[12px] text-slate-400">PDF, DOCX, MD, TXT</p>
      </div>
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
    <div className="flex flex-col h-full p-6 space-y-5">
      {/* Stats row */}
      {stats && (
        <div className="flex gap-4 text-[12.5px] text-slate-600 flex-wrap">
          <span>Всего: <strong className="text-slate-900 font-semibold">{stats.total_documents}</strong></span>
          <span className="text-slate-300">·</span>
          <span>Актуальных: <strong className="text-emerald-700 font-semibold">{stats.by_status.actual}</strong></span>
          <span className="text-slate-300">·</span>
          <span>Расхождений: <strong className="text-amber-700 font-semibold">{stats.open_contradictions}</strong></span>
          <span className="text-slate-300">·</span>
          <span>Обещаний: <strong className="text-sky-700 font-semibold">{stats.open_promises}</strong></span>
        </div>
      )}

      <UploadZone />

      {/* Filter pills */}
      <div className="flex gap-2 flex-wrap">
        {['', 'actual', 'draft', 'archived', 'unknown'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={clsx(
              'px-3 py-1 rounded-full text-[12px] font-medium transition-colors duration-120 border',
              statusFilter === s
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400',
            )}
          >
            {s || 'Все'}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-soft">
        <table className="w-full text-left">
          <thead className="bg-slate-50 text-[11px] text-slate-500 uppercase tracking-wider border-b border-slate-200">
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
          <p className="text-center py-10 text-[13.5px] text-slate-400">Нет документов</p>
        )}
      </div>
    </div>
  )
}
