import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLogicSignals, updateLogicSignal } from '../api/client'
import type { LogicSignal } from '../types'
import clsx from 'clsx'

const TYPE_LABEL: Record<string, string> = {
  strategic: 'Стратегический',
  operational: 'Операционный',
  priority: 'Приоритет',
  client: 'Клиентский',
}

const TYPE_COLOR: Record<string, string> = {
  strategic: 'bg-blue-900/50 text-blue-300',
  operational: 'bg-orange-900/50 text-orange-300',
  priority: 'bg-purple-900/50 text-purple-300',
  client: 'bg-emerald-900/50 text-emerald-300',
}

const STATUS_COLOR: Record<string, string> = {
  open: 'bg-yellow-900/60 text-yellow-300',
  reviewed: 'bg-emerald-900/60 text-emerald-300',
  dismissed: 'bg-zinc-700 text-zinc-400',
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.8 ? 'bg-red-500' : value >= 0.65 ? 'bg-yellow-500' : 'bg-zinc-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-400 w-8 text-right">{pct}%</span>
    </div>
  )
}

function SignalCard({ item }: { item: LogicSignal }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState('')
  const [showNotes, setShowNotes] = useState(false)

  const mut = useMutation({
    mutationFn: ({ status, review_notes }: { status: 'reviewed' | 'dismissed'; review_notes?: string }) =>
      updateLogicSignal(item.id, status, review_notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['logic-signals'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-800/50 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx('text-xs px-2 py-0.5 rounded font-medium', TYPE_COLOR[item.signal_type])}>
            {TYPE_LABEL[item.signal_type] ?? item.signal_type}
          </span>
          <span className={clsx('text-xs px-2 py-0.5 rounded', STATUS_COLOR[item.status])}>
            {item.status}
          </span>
        </div>
        <span className="text-xs text-zinc-500 whitespace-nowrap shrink-0">
          {new Date(item.created_at).toLocaleDateString('ru')}
        </span>
      </div>

      <ConfidenceBar value={item.confidence} />

      {/* Два утверждения */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-zinc-600 bg-zinc-900/40 p-3 space-y-1.5">
          <div className="text-xs font-medium text-blue-400 truncate" title={item.document_a.title}>
            {item.document_a.title}
          </div>
          <p className="text-sm text-zinc-200 leading-snug">{item.statement_a}</p>
        </div>
        <div className="rounded-lg border border-zinc-600 bg-zinc-900/40 p-3 space-y-1.5">
          <div className="text-xs font-medium text-purple-400 truncate" title={item.document_b.title}>
            {item.document_b.title}
          </div>
          <p className="text-sm text-zinc-200 leading-snug">{item.statement_b}</p>
        </div>
      </div>

      {item.review_notes && (
        <p className="text-xs text-zinc-400 italic border-l-2 border-zinc-600 pl-3">{item.review_notes}</p>
      )}

      {item.status === 'open' && (
        <div className="space-y-2">
          {showNotes && (
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Комментарий к решению (необязательно)"
              rows={2}
              className="w-full text-xs bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none focus:border-zinc-500"
            />
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (!showNotes) { setShowNotes(true); return }
                mut.mutate({ status: 'reviewed', review_notes: notes || undefined })
              }}
              disabled={mut.isPending}
              className="text-xs px-3 py-1.5 rounded bg-emerald-700/50 text-emerald-300 hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              Рассмотрено ✓
            </button>
            <button
              onClick={() => mut.mutate({ status: 'dismissed', review_notes: notes || undefined })}
              disabled={mut.isPending}
              className="text-xs px-3 py-1.5 rounded bg-zinc-700 text-zinc-400 hover:bg-zinc-600 transition-colors disabled:opacity-50"
            >
              Не релевантно
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function LogicSignalsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('open')
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['logic-signals', statusFilter],
    queryFn: () => getLogicSignals(statusFilter || undefined),
  })

  return (
    <div className="flex flex-col h-full p-6 space-y-6 overflow-y-auto">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">Логические сигналы</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Сигналы к проверке возможных расхождений в подходах
          </p>
        </div>
        <span className="text-sm text-zinc-400">{items.length} записей</span>
      </div>

      <div className="flex gap-2">
        {[
          { v: 'open', label: 'Открытые' },
          { v: 'reviewed', label: 'Рассмотренные' },
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
          <p className="text-sm">Сигналов нет — загрузи документы для анализа</p>
        </div>
      )}

      <div className="space-y-4">
        {items.map((item) => (
          <SignalCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  )
}
