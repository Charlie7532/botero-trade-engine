/**
 * Shared tile shell used by every dashboard widget.
 * Server component — pure presentational.
 */
import type { ReactNode } from 'react'

type Props = {
  title: string
  subtitle?: string
  /** Top-right slot (e.g. current value, badge). */
  accessory?: ReactNode
  className?: string
  children: ReactNode
}

export function Tile({ title, subtitle, accessory, className, children }: Props) {
  return (
    <section
      className={`bg-surface border border-border rounded-2xl p-5 flex flex-col gap-4 ${className ?? ''}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">{title}</p>
          {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
        </div>
        {accessory && <div className="text-right">{accessory}</div>}
      </header>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  )
}

export function TileEmpty({ message }: { message: string }) {
  return (
    <div className="h-full min-h-[120px] flex items-center justify-center text-xs text-muted">
      {message}
    </div>
  )
}
