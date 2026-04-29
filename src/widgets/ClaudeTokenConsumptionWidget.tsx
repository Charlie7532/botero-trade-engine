import type { WidgetServerProps } from 'payload'

type TokenSnapshot = {
  cacheCreationTokens: number
  cacheReadTokens: number
  inputTokens: number
  model: null | string
  outputTokens: number
  updatedAt: null | string
}

const cardStyle = {
  background: 'linear-gradient(135deg, rgba(8, 51, 68, 0.96), rgba(18, 27, 36, 0.96))',
  border: '1px solid rgba(108, 214, 255, 0.2)',
  borderRadius: '20px',
  boxShadow: '0 18px 48px rgba(4, 14, 24, 0.28)',
  color: '#e9f7ff',
  overflow: 'hidden',
}

const headerStyle = {
  alignItems: 'center',
  display: 'flex',
  justifyContent: 'space-between',
  gap: '1rem',
}

const gridStyle = {
  display: 'grid',
  gap: '0.85rem',
  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
  marginTop: '1.25rem',
}

const metricStyle = {
  background: 'rgba(255, 255, 255, 0.06)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: '16px',
  padding: '0.9rem 1rem',
}

function readIntegerEnv(name: keyof NodeJS.ProcessEnv): number {
  const value = process.env[name]

  if (!value) {
    return 0
  }

  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : 0
}

function getTokenSnapshot(): TokenSnapshot | null {
  const inputTokens = readIntegerEnv('CLAUDE_CODE_INPUT_TOKENS')
  const outputTokens = readIntegerEnv('CLAUDE_CODE_OUTPUT_TOKENS')
  const cacheCreationTokens = readIntegerEnv('CLAUDE_CODE_CACHE_CREATION_TOKENS')
  const cacheReadTokens = readIntegerEnv('CLAUDE_CODE_CACHE_READ_TOKENS')

  if (inputTokens + outputTokens + cacheCreationTokens + cacheReadTokens === 0) {
    return null
  }

  return {
    inputTokens,
    outputTokens,
    cacheCreationTokens,
    cacheReadTokens,
    model: process.env.CLAUDE_CODE_MODEL ?? null,
    updatedAt: process.env.CLAUDE_CODE_UPDATED_AT ?? null,
  }
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatRelativeDate(value: null | string): null | string {
  if (!value) {
    return null
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return null
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <div style={metricStyle}>
      <div style={{ color: 'rgba(233, 247, 255, 0.72)', fontSize: '0.76rem', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {props.label}
      </div>
      <div style={{ fontSize: '1.3rem', fontWeight: 700, marginTop: '0.35rem' }}>{props.value}</div>
    </div>
  )
}

export default async function ClaudeTokenConsumptionWidget({ widgetSlug }: WidgetServerProps) {
  const snapshot = getTokenSnapshot()

  if (!snapshot) {
    return (
      <section style={cardStyle}>
        <div style={{ padding: '1.35rem 1.4rem 1.5rem' }}>
          <div style={headerStyle}>
            <div>
              <div style={{ color: '#8fdfff', fontSize: '0.78rem', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                {widgetSlug.replace(/-/g, ' ')}
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: '0.35rem 0 0' }}>Instrumentation pending</h3>
            </div>
            <div style={{ background: 'rgba(255, 255, 255, 0.08)', borderRadius: '999px', fontSize: '0.78rem', padding: '0.35rem 0.7rem' }}>
              No token feed
            </div>
          </div>
          <p style={{ color: 'rgba(233, 247, 255, 0.76)', lineHeight: 1.55, margin: '1rem 0 0' }}>
            Set CLAUDE_CODE_INPUT_TOKENS, CLAUDE_CODE_OUTPUT_TOKENS, CLAUDE_CODE_CACHE_CREATION_TOKENS,
            and CLAUDE_CODE_CACHE_READ_TOKENS in the runtime environment to surface live Claude usage here.
          </p>
        </div>
      </section>
    )
  }

  const totalTokens = snapshot.inputTokens + snapshot.outputTokens + snapshot.cacheCreationTokens + snapshot.cacheReadTokens
  const updatedAt = formatRelativeDate(snapshot.updatedAt)

  return (
    <section style={cardStyle}>
      <div style={{ padding: '1.35rem 1.4rem 1.5rem' }}>
        <div style={headerStyle}>
          <div>
            <div style={{ color: '#8fdfff', fontSize: '0.78rem', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
              Claude session telemetry
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: '0.35rem 0 0' }}>
              {snapshot.model ?? 'Claude'} token consumption
            </h3>
          </div>
          <div style={{ background: 'rgba(255, 255, 255, 0.08)', borderRadius: '999px', fontSize: '0.78rem', padding: '0.35rem 0.7rem' }}>
            Env source
          </div>
        </div>

        <div style={gridStyle}>
          <MetricCard label="Total" value={formatNumber(totalTokens)} />
          <MetricCard label="Input" value={formatNumber(snapshot.inputTokens)} />
          <MetricCard label="Output" value={formatNumber(snapshot.outputTokens)} />
          <MetricCard label="Cache Write" value={formatNumber(snapshot.cacheCreationTokens)} />
          <MetricCard label="Cache Read" value={formatNumber(snapshot.cacheReadTokens)} />
        </div>

        <p style={{ color: 'rgba(233, 247, 255, 0.76)', lineHeight: 1.55, margin: '1rem 0 0' }}>
          {updatedAt ? `Last updated ${updatedAt}.` : 'Updated timestamp not provided.'}
        </p>
      </div>
    </section>
  )
}