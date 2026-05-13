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
          'fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm transition-opacity duration-200',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        )}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={clsx(
          'fixed top-0 right-0 z-50 h-full bg-white border-l border-slate-200 flex flex-col shadow-card transition-transform duration-300 ease-in-out',
          width,
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 shrink-0">
          <span className="text-[14px] font-semibold text-slate-900">{title}</span>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition-colors p-1 rounded ring-focus"
            aria-label="Закрыть"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width={16} height={16} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto nice-scroll bg-[#f6f7f9]">{children}</div>
      </div>
    </>
  )
}
