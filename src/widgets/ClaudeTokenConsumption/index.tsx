import type { WidgetServerProps } from 'payload'

type UsageBucket = {
  cache_creation_input_tokens: number
  cache_read_input_tokens: number
  output_tokens: number
  started_at: string
  uncached_input_tokens: number
}

type UsageResponse = {
  data: UsageBucket[]
}

type CostBucket = {
  cost_cents: string
  started_at: string
}

type CostResponse = {
  data: CostBucket[]
}

function num(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const p = Number(v)
    return Number.isFinite(p) ? p : 0
  }
  return 0
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return new Intl.NumberFormat('en-US').format(value)
}

async function fetchUsage(): Promise<{ buckets: UsageBucket[]; error: string | null }> {
  const adminKey = process.env.ANTHROPIC_ADMIN_KEY
  if (!adminKey) return { buckets: [], error: 'ANTHROPIC_ADMIN_KEY not set' }

  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  const params = new URLSearchParams({
    starting_at: sevenDaysAgo.toISOString(),
    ending_at: now.toISOString(),
    bucket_width: '1d',
  })

  try {
    const res = await fetch(
      `https://api.anthropic.com/v1/organizations/usage_report/messages?${params}`,
      {
        headers: { 'anthropic-version': '2023-06-01', 'x-api-key': adminKey },
        next: { revalidate: 300 },
      },
    )
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      return { buckets: [], error: `API ${res.status}: ${text.slice(0, 120)}` }
    }
    const json = (await res.json()) as UsageResponse
    return { buckets: json.data ?? [], error: null }
  } catch (err) {
    return { buckets: [], error: err instanceof Error ? err.message : 'Fetch error' }
  }
}

async function fetchCost(): Promise<{ costCents7d: number; costCentsToday: number }> {
  const adminKey = process.env.ANTHROPIC_ADMIN_KEY
  if (!adminKey) return { costCents7d: 0, costCentsToday: 0 }

  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const params = new URLSearchParams({
    starting_at: sevenDaysAgo.toISOString(),
    ending_at: now.toISOString(),
    bucket_width: '1d',
  })

  try {
    const res = await fetch(
      `https://api.anthropic.com/v1/organizations/cost_report?${params}`,
      {
        headers: { 'anthropic-version': '2023-06-01', 'x-api-key': adminKey },
        next: { revalidate: 300 },
      },
    )
    if (!res.ok) return { costCents7d: 0, costCentsToday: 0 }
    const json = (await res.json()) as CostResponse
    const buckets = json.data ?? []
    const costCents7d = buckets.reduce((s, b) => s + num(b.cost_cents), 0)
    const costCentsToday = buckets
      .filter((b) => new Date(b.started_at) >= todayStart)
      .reduce((s, b) => s + num(b.cost_cents), 0)
    return { costCents7d, costCentsToday }
  } catch {
    return { costCents7d: 0, costCentsToday: 0 }
  }
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'var(--theme-elevation-50)',
        borderRadius: '8px',
        padding: '0.75rem 0.85rem',
      }}
    >
      <div style={{ color: 'var(--theme-elevation-500)', fontSize: '0.7rem', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.15rem', fontWeight: 600, marginTop: '0.2rem' }}>
        {value}
      </div>
    </div>
  )
}

export default async function ClaudeTokenConsumptionWidget({ widgetSlug }: WidgetServerProps) {
  const [{ buckets, error }, { costCents7d, costCentsToday }] = await Promise.all([
    fetchUsage(),
    fetchCost(),
  ])

  if (error) {
    const isMissingKey = error.includes('not set')

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>
            {isMissingKey ? 'Admin key required' : 'Usage unavailable'}
          </h4>
          <span
            style={{
              background: 'var(--theme-elevation-100)',
              borderRadius: '4px',
              color: 'var(--theme-elevation-500)',
              fontSize: '0.7rem',
              padding: '0.2rem 0.5rem',
            }}
          >
            {isMissingKey ? 'Not configured' : 'Error'}
          </span>
        </div>
        <p style={{ color: 'var(--theme-elevation-500)', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
          {isMissingKey
            ? 'Add ANTHROPIC_ADMIN_KEY to .env — generate at console.anthropic.com → Settings → Admin Keys (sk-ant-admin…).'
            : error}
        </p>
      </div>
    )
  }

  const totals = buckets.reduce(
    (acc, b) => ({
      input: acc.input + num(b.uncached_input_tokens),
      output: acc.output + num(b.output_tokens),
      cacheWrite: acc.cacheWrite + num(b.cache_creation_input_tokens),
      cacheRead: acc.cacheRead + num(b.cache_read_input_tokens),
    }),
    { cacheRead: 0, cacheWrite: 0, input: 0, output: 0 },
  )

  const totalTokens = totals.input + totals.output + totals.cacheWrite + totals.cacheRead
  const cacheHitRate =
    totals.cacheRead + totals.cacheWrite + totals.input > 0
      ? totals.cacheRead / (totals.cacheRead + totals.cacheWrite + totals.input)
      : 0

  const spend7d = (costCents7d / 100).toFixed(2)
  const spendToday = (costCentsToday / 100).toFixed(2)
  const daysWithData = buckets.filter(
    (b) => num(b.uncached_input_tokens) + num(b.output_tokens) + num(b.cache_creation_input_tokens) + num(b.cache_read_input_tokens) > 0,
  ).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
        <div>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Claude usage</h4>
          <span style={{ color: 'var(--theme-elevation-500)', fontSize: '0.72rem' }}>Last 7 days</span>
        </div>
        <span
          style={{
            background: 'var(--theme-elevation-100)',
            borderRadius: '4px',
            color: 'var(--theme-elevation-500)',
            fontSize: '0.7rem',
            padding: '0.2rem 0.5rem',
          }}
        >
          Admin API
        </span>
      </div>

      <div style={{ display: 'grid', gap: '0.5rem', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
        <Metric label="7d Spend" value={`$${spend7d}`} />
        <Metric label="Today" value={`$${spendToday}`} />
        <Metric label="Tokens" value={formatTokens(totalTokens)} />
        <Metric label="Input" value={formatTokens(totals.input)} />
        <Metric label="Output" value={formatTokens(totals.output)} />
        <Metric label="Cache Write" value={formatTokens(totals.cacheWrite)} />
        <Metric label="Cache Read" value={formatTokens(totals.cacheRead)} />
        <Metric label="Cache Hit" value={`${(cacheHitRate * 100).toFixed(1)}%`} />
      </div>

      <span style={{ color: 'var(--theme-elevation-500)', fontSize: '0.72rem' }}>
        {daysWithData > 0 ? `${daysWithData} active day${daysWithData > 1 ? 's' : ''} · refreshes every 5 min` : 'No usage in this period'}
      </span>
    </div>
  )
}