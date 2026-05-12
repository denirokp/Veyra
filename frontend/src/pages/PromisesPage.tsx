import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPromises } from '../api/client'
import axios from 'axios'
import clsx from 'clsx'

type PromiseStatus = 'open' | 'fulfilled' | 'overdue' | 'no_data'

const STATUS_COLOR: Record<PromiseStatus, string> = {
  open: 'bg-blue-900/60 text-blue-300',
  fulfilled: 'bg-emerald-900/60 text-emerald-300',
  overdue: 'bg-red-900/60 text-red-300',
  no_data: 'bg-zinc-700 text-zinc-400',
}

const STATUS_LABEL: Record<PromiseStatus, string> = {
  open: 'Открыто',
  fulfilled: 'Выполнено',
  overdue: 'Просрочено',
  no_data: 'Нет данных',
}

interface PromiseItem {
  id: string
  text: string
  normalized_text: string
  document: { id: string; title: string }
  document_date: string | null
  deadline: string | null
  metric: string | null
  target_value: number | null
  status: PromiseStatus
  resolved_at: string | null
  notes: string | null
}

function isOverdue(deadline: string | null, status: PromiseStatus): boolean {
  if (status !== 'open' || !deadline) return false
  return new Date(deadline) < new Date()
}

function PromiseRow({ item }: { item: PromiseItem }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState(item.notes ?? '')
  const [editing, setEditing] = useState(false)

  const mut = useMutation({
    mutationFn: (newStatus: PromiseStatus) =>
      axios.patch(`/api/promises/${item.id}`, {
        status: newStatus,
        notes: notes || undefined,
        resolved_at: newStatus === 'fulfilled' ? new Date().toISOString().slice(0, 10) : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['promises'] })
      setEditing(false)
    },
  })

  const effectiveStatus =
    isOverdue(item.deadline, item.status) ? 'overdue' : item.status

  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-800/50 p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <span className={clsx('text-xs px-2 py-0.5 rounded shrink-0', STATUS_COLOR[effectiveStatus])}>
          {STATUS_LABEL[effectiveStatus]}
        </span>
        <div className="flex gap-3 text-xs text-zinc-500 shrink-0">
          {item.deadline && (
            <span className={isOverdue(item.deadline, item.status) ? 'text-red-400' : ''}>
              срок: {item.deadline}
            </span>
          )}
          {item.document_date && <span>из {item.document_date}</span>}
        </div>
      </div>

      <p className="text-sm text-zinc-200 leading-relaxed">{item.text}</p>

      {item.metric && (
        <p className="text-xs text-zinc-400">
          Цель: <span className="text-blue-300">{item.metric}
          {item.target_value != null ? ` = ${item.target_value}` : ''}</span>
        </p>
      )}

      <p className="text-xs text-zinc-500 truncate" title={item.document.title}>
        📄 {item.document.title}
      </p>

      {/* Действия */}
      {item.status === 'open' && (
        <div className="flex gap-2 flex-wrap pt-1">
          <button
            onClick={() => mut.mutate('fulfilled')}
            className="text-xs px-3 py-1 rounded bg-emerald-800/50 text-emerald-300 hover:bg-emerald-800 transition-colors"
          >
            ✓ Выполнено
          </button>
          <button
            onClick={() => mut.mutate('no_data')}
            className="text-xs px-3 py-1 rounded bg-zinc-700 text-zinc-400 hover:bg-zinc-600 transition-colors"
          >
            Нет данных
          </button>
          <button
            onClick={() => setEditing(!editing)}
            className="text-xs px-3 py-1 rounded border border-zinc-600 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Заметка
          </button>
        </div>
      )}

      {editing && (
        <div className="flex gap-2">
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Комментарий к статусу..."
            className="flex-1 text-xs bg-zinc-700 rounded px-3 py-2 text-zinc-200 placeholder-zinc-500 border border-zinc-600 outline-none"
          />
          <button
            onClick={() => mut.mutate(item.status)}
            className="text-xs px-3 py-1 rounded bg-blue-700 text-white hover:bg-blue-600"
          >
            Сохранить
          </button>
        </div>
      )}

      {item.notes && !editing && (
        <p className="text-xs text-zinc-500 italic">{item.notes}</p>
      )}
    </div>
  )
}

export function PromisesPage() {
  const [statusFilter, setStatusFilter] = useState<string>('open')
  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['promises', statusFilter],
    queryFn: () => getPromises(statusFilter || undefined),
  })

  const items = raw as PromiseItem[]
  // Поднимаем просроченные наверх
  const sorted = [...items].sort((a, b) => {
    const aOver = isOverdue(a.deadline, a.status) ? -1 : 0
    const bOver = isOverdue(b.deadline, b.status) ? -1 : 0
    return aOver - bOver
  })

  const overdueCount = items.filter((i) => isOverdue(i.deadline, i.status)).length

  return (
    <div className="flex flex-col h-full p-6 space-y-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-100">Реестр обещаний</h2>
        <div className="flex gap-3 text-sm text-zinc-400">
          {overdueCount > 0 && (
            <span className="text-red-400 font-medium">⚠ {overdueCount} просрочено</span>
          )}
          <span>{items.length} записей</span>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {[
          { v: 'open', label: 'Открытые' },
          { v: 'fulfilled', label: 'Выполненные' },
          { v: 'overdue', label: 'Просроченные' },
          { v: 'no_data', label: 'Нет данных' },
          { v: '', label: 'Все' },
        ].map(({ v, label }) => (
          <button
            key={v}
            onClick={() => setStatusFilter(v)}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              statusFilter === v
                ? 'bg-blue-600 text-white'
                : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-zinc-500 text-sm">Загрузка...</p>}

      {!isLoading && sorted.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 space-y-2">
          <p className="text-2xl">📋</p>
          <p className="text-sm">Нет обещаний в этом фильтре</p>
        </div>
      )}

      <div className="space-y-3">
        {sorted.map((item) => <PromiseRow key={item.id} item={item} />)}
      </div>
    </div>
  )
}
