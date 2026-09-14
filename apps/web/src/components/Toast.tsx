import React from 'react'
import { IconAlert, IconCheck, IconInfo, IconX } from './icons'

export type ToastTone = 'info' | 'success' | 'warning' | 'danger'

export type ToastItem = {
  id: string
  tone: ToastTone
  message: string
}

type ToastContextValue = {
  notify: (message: string, tone?: ToastTone) => void
}

const ToastContext = React.createContext<ToastContextValue | null>(null)

const ICONS: Record<ToastTone, React.ReactNode> = {
  info: <IconInfo size={13} />,
  success: <IconCheck size={13} />,
  warning: <IconAlert size={13} />,
  danger: <IconX size={13} />,
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([])
  const [leaving, setLeaving] = React.useState<Set<string>>(new Set())
  const timers = React.useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = React.useCallback((id: string) => {
    setLeaving(prev => new Set(prev).add(id))
    window.setTimeout(() => {
      setToasts(list => list.filter(item => item.id !== id))
      setLeaving(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }, 200)
  }, [])

  const notify = React.useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = `toast_${Date.now()}_${Math.random().toString(16).slice(2, 6)}`
      setToasts(list => [...list, { id, tone, message }])
      const timer = window.setTimeout(() => dismiss(id), 4200)
      timers.current.set(id, timer)
    },
    [dismiss],
  )

  React.useEffect(() => {
    const map = timers.current
    return () => {
      map.forEach(timer => window.clearTimeout(timer))
      map.clear()
    }
  }, [])

  const value = React.useMemo(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" role="region" aria-label="通知" aria-live="polite">
        {toasts.map(item => (
          <div
            key={item.id}
            className={`toast ${item.tone} ${leaving.has(item.id) ? 'leaving' : ''}`}
          >
            <span className="toast-icon" aria-hidden="true">
              {ICONS[item.tone]}
            </span>
            <div className="toast-body">
              <p>{item.message}</p>
            </div>
            <button
              className="toast-close"
              aria-label="关闭通知"
              onClick={() => dismiss(item.id)}
            >
              <IconX size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext)
  if (!ctx) return { notify: () => undefined }
  return ctx
}
