import clsx from 'clsx'

interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  width?: string
  children: React.ReactNode
}

export function Drawer({ open, onClose, title, width = 'w-[680px]', children }: DrawerProps) {
  return (
    <>
      {/* Backdrop */}
      <div
        className={clsx(
          'fixed inset-0 z-40 bg-black/50 transition-opacity duration-300',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        )}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={clsx(
          'fixed top-0 right-0 z-50 h-full bg-zinc-900 border-l border-zinc-700 flex flex-col transition-transform duration-300 ease-in-out',
          width,
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-700 shrink-0">
          <span className="text-sm font-semibold text-zinc-100">{title}</span>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </>
  )
}
