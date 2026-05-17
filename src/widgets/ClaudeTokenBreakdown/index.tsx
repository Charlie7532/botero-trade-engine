import type { WidgetServerProps } from 'payload'

import { bucketTokens, formatTokens, loadClaudeUsage } from '../ClaudeTokenConsumption/api'

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'var(--theme-elevation-50)',
        borderRadius: 8,
        minWidth: 0,
        padding: '0.65rem 0.8rem',
      }}
    >
      <div
        style={{
          color: 'var(--theme-elevation-500)',
          fontSize: '0.65rem',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '1.05rem', fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  )
}

export default async function ClaudeTokenBreakdownWidget(_props: WidgetServerProps) {
  const snap = await loadClaudeUsage()

  if (snap.error) {
    const isMissingKey = snap.error === 'missing-key'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>
          {isMissingKey ? 'Admin key required' : 'Tokens unavailable'}
        </h4>
        <p
          style={{
            color: 'var(--theme-elevation-500)',
            fontSize: '0.82rem',
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          {isMissingKey
            ? 'Add ANTHROPIC_ADMIN_KEY to .env.local to populate token usage.'
            : 'Could not reach the Anthropic Admin API.'}
        </p>
      </div>
    )
  }

  const { scope, workspaceName, orgName } = snap

  // Aggregate last-7-day usage tokens client-style from the wide window.
  const now = new Date()
  const todayUtcStart = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
  const sevenAgo = new Date(todayUtcStart.getTime() - 6 * 86400000)
  const tomorrow = new Date(todayUtcStart.getTime() + 86400000)
  const tokens = snap.usageBuckets
    .filter((b) => {
      const t = new Date(b.starting_at).getTime()
      return Number.isFinite(t) && t >= sevenAgo.getTime() && t < tomorrow.getTime()
    })
    .reduce(
      (a, b) => {
        const t = bucketTokens(b)
        return {
          input: a.input + t.input,
          output: a.output + t.output,
          cacheRead: a.cacheRead + t.cacheRead,
          cacheWrite: a.cacheWrite + t.cacheWrite,
        }
      },
      { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    )
  const totalTokens = tokens.input + tokens.output + tokens.cacheRead + tokens.cacheWrite
  const cacheDenom = tokens.cacheRead + tokens.cacheWrite + tokens.input
  const cacheHitRate = cacheDenom > 0 ? tokens.cacheRead / cacheDenom : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div
        style={{
          alignItems: 'center',
          display: 'flex',
          gap: '0.5rem',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Token breakdown</h4>
          <span style={{ color: 'var(--theme-elevation-500)', fontSize: '0.72rem' }}>
            Last 7 days
            {scope === 'workspace' && workspaceName
              ? ` · ${workspaceName}`
              : orgName
                ? ` · ${orgName} (org-wide)`
                : ''}
          </span>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gap: '0.5rem',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
        }}
      >
        <Metric label="Tokens" value={formatTokens(totalTokens)} />
        <Metric label="Input" value={formatTokens(tokens.input)} />
        <Metric label="Output" value={formatTokens(tokens.output)} />
        <Metric label="Cache write" value={formatTokens(tokens.cacheWrite)} />
        <Metric label="Cache read" value={formatTokens(tokens.cacheRead)} />
        <Metric label="Cache hit" value={`${(cacheHitRate * 100).toFixed(1)}%`} />
      </div>
    </div>
  )
}
