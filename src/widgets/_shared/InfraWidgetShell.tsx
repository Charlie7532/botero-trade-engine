import type { ReactNode } from 'react'

type Props = {
  title: string
  badge?: string
  badgeTitle?: string
  children: ReactNode
  footer?: ReactNode
}

/** Shared shell used by all infra widgets — same header style as PostgresPerformance. */
export default function InfraWidgetShell({ title, badge, badgeTitle, children, footer }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
      <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>{title}</h4>
        {badge && (
          <span
            style={{
              background: 'var(--theme-elevation-100)',
              borderRadius: '4px',
              color: 'var(--theme-elevation-500)',
              fontSize: '0.7rem',
              padding: '0.2rem 0.5rem',
            }}
            title={badgeTitle}
          >
            {badge}
          </span>
        )}
      </div>
      {children}
      {footer && (
        <div
          style={{
            color: 'var(--theme-elevation-500)',
            fontSize: '0.7rem',
            lineHeight: 1.4,
          }}
        >
          {footer}
        </div>
      )}
    </div>
  )
}
