import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getContradictions } from '../api/client'
import axios from 'axios'
import clsx from 'clsx'

type Status = 'open' | 'resolved' | 'dismissed'

const STATUS_COLOR: Record<Status, string> = {
  open: 'bg-yellow-900/60 text-yellow-300',
  resolved: 'bg-emerald-900/60 text-emerald-300',
  dismissed: 'bg-zinc-700 text-zinc-400',
}

function resolve(id: string, winnerDocId: string, status: 'resolved' | 'dismissed') {
  return axios.patch(`/api/contradictions/${id}`, { status, resolved_by: winnerDocId })
}

interface ContradictionItem {
  id: string
  metric: string
  value_a: string
  value_b: string
  document_a: { id: string; title: string }
  document_b: { id: string; title: string }
  status: Status
  created_at: string
}

function ContradictionRow({ item }: { item: ContradictionItem }) {
  const qc = useQueryClient()
  const mut = useMutation({
    mutationFn: ({ winnerId, status }: { winnerId: string; status: 'resolved' | 'dismissed' }) =>
      resolve(item.id, winnerId, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contradictions'] }),
  })

  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-800/50 p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-sm font-medium text-zinc-100">{item.metric}</span>
          <span className={clsx('ml-3 text-xs px-2 py-0.5 rounded', STATUS_COLOR[item.status])}>
            {item.status}
          </span>
        </div>
        <span className="text-xs text-zinc-500 whitespace-nowrap">
          {new Date(item.created_at).toLocaleDateString('ru')}
        </span>
      </div>

      {/* Сравнение значений */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-zinc-600 p-3 space-y-2">
          <div className="text-lg font-bold text-blue-400">{item.value_a ?? '—'}</div>
          <div className="text-xs text-zinc-400 truncate" title={item.document_a.title}>
            {item.document_a.title}
          </div>
          {item.status === 'open' && (
            <button
              onClick={() => mut.mutate({ winnerId: item.document_a.id, status: 'resolved' })}
              className="text-xs px-3 py-1 rounded bg-blue-700/50 text-blue-300 hover:bg-blue-700 transition-colors"
            >
              Этот верный ✓
            </button>
          )}
        </div>
        <div className="rounded-lg border border-zinc-600 p-3 space-y-2">
          <div className="text-lg font-bold text-purple-400">{item.value_b ?? '—'}</div>
          <div className="text-xs text-zinc-400 truncate" title={item.document_b.title}>
            {item.document_b.title}
          </div>
          {item.status === 'open' && (
            <button
              onClick={() => mut.mutate({ winnerId: item.document_b.id, status: 'resolved' })}
              className="text-xs px-3 py-1 rounded bg-purple-700/50 text-purple-300 hover:bg-purple-700 transition-colors"
            >
              Этот верный ✓
            </button>
          )}
        </div>
      </div>

      {item.status === 'open' && (
        <button
          onClick={() => mut.mutate({ winnerId: '', status: 'dismissed' })}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Не является расхождением — отклонить
        </button>
      )}
    </div>
  )
}

export function ContradictionsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('open')
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['contradictions', statusFilter],
    queryFn: () => getContradictions(statusFilter || undefined),
  })

  return (
    <div className="flex flex-col h-full p-6 space-y-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-100">Числовые расхождения</h2>
        <span className="text-sm text-zinc-400">{items.length} записей</span>
      </div>

      <div className="flex gap-2">
        {[
          { v: 'open', label: 'Открытые' },
          { v: 'resolved', label: 'Решённые' },
          { v: 'dismissed', label: 'Отклонённые' },
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

      {!isLoading && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 space-y-2">
          <p className="text-2xl">✓</p>
          <p className="text-sm">Расхождений нет — загрузи документы для анализа</p>
        </div>
      )}

      <div className="space-y-4">
        {(items as ContradictionItem[]).map((item) => (
          <ContradictionRow key={item.id} item={item} />
        ))}
      </div>
    </div>
  )
}
