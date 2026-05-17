import type { WidgetServerProps } from 'payload'

import ClaudeUsageInteractive from './ClaudeUsageInteractive'
import { loadClaudeUsage } from './api'

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        background: 'var(--theme-elevation-100)',
        borderRadius: 999,
        color: 'var(--theme-elevation-500)',
        fontSize: '0.68rem',
        padding: '0.18rem 0.55rem',
      }}
    >
      {children}
    </span>
  )
}

function ErrorCard({ kind }: { kind: 'missing-key' | 'fetch-failed' }) {
  const isMissingKey = kind === 'missing-key'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>
          {isMissingKey ? 'Admin key required' : 'Usage unavailable'}
        </h4>
        <Pill>{isMissingKey ? 'Not configured' : 'Error'}</Pill>
      </div>
      <p
        style={{
          color: 'var(--theme-elevation-500)',
          fontSize: '0.82rem',
          lineHeight: 1.5,
          margin: 0,
        }}
      >
        {isMissingKey
          ? 'Add ANTHROPIC_ADMIN_KEY to .env.local — generate at console.anthropic.com → Settings → Admin Keys (sk-ant-admin…).'
          : 'Could not reach the Anthropic Admin API. Check the admin key and network access.'}
      </p>
    </div>
  )
}

export default async function ClaudeTokenConsumptionWidget(_props: WidgetServerProps) {
  const snap = await loadClaudeUsage()
  if (snap.error) return <ErrorCard kind={snap.error} />
  return <ClaudeUsageInteractive snap={snap} />
}
