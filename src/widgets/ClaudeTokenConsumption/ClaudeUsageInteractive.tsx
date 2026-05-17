'use client'

import { useMemo, useState } from 'react'

import SpendChart, { type SpendPoint } from './SpendChart'
import {
  bucketCostUsd,
  bucketTokens,
  formatTokens,
  type ClaudeUsageSnapshot,
  type CostBucket,
} from './api'

type RangeKey = 'today' | '7d' | '30d' | 'mtd' | 'last-month' | '90d'
type GroupKey = 'day' | 'month'

const RANGE_OPTIONS: { value: RangeKey; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'mtd', label: 'Month to date' },
  { value: 'last-month', label: 'Last month' },
  { value: '90d', label: 'Last 90 days' },
]

const GROUP_OPTIONS: { value: GroupKey; label: string }[] = [
  { value: 'day', label: 'Daily' },
  { value: 'month', label: 'Monthly' },
]

function Stat({
  label,
  value,
  hint,
  emphasized = false,
}: {
  label: string
  value: string
  hint?: string
  emphasized?: boolean
}) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          color: 'var(--theme-elevation-500)',
          fontSize: '0.68rem',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: emphasized ? '1.65rem' : '1.05rem',
          fontWeight: emphasized ? 600 : 500,
          letterSpacing: emphasized ? '-0.015em' : '0',
          lineHeight: 1.15,
          marginTop: 2,
        }}
      >
        {value}
      </div>
      {hint ? (
        <div style={{ color: 'var(--theme-elevation-400)', fontSize: '0.7rem', marginTop: 2 }}>
          {hint}
        </div>
      ) : null}
    </div>
  )
}

function Select<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  label: string
}) {
  return (
    <label style={{ alignItems: 'center', display: 'flex', gap: '0.4rem' }}>
      <span
        style={{
          color: 'var(--theme-elevation-500)',
          fontSize: '0.68rem',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
      <select
        onChange={(e) => onChange(e.target.value as T)}
        style={{
          background: 'var(--theme-elevation-50)',
          border: '1px solid var(--theme-elevation-150)',
          borderRadius: 6,
          color: 'var(--theme-text)',
          fontSize: '0.78rem',
          padding: '0.25rem 0.45rem',
        }}
        value={value}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/** Compute [start, endExclusive) UTC window for a given range key. */
function computeRange(range: RangeKey): { from: Date; to: Date } {
  const now = new Date()
  const todayUtc = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
  const tomorrowUtc = new Date(todayUtc.getTime() + 24 * 60 * 60 * 1000)

  switch (range) {
    case 'today':
      return { from: todayUtc, to: tomorrowUtc }
    case '7d':
      return { from: new Date(todayUtc.getTime() - 6 * 86400000), to: tomorrowUtc }
    case '30d':
      return { from: new Date(todayUtc.getTime() - 29 * 86400000), to: tomorrowUtc }
    case 'mtd':
      return {
        from: new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)),
        to: tomorrowUtc,
      }
    case 'last-month': {
      const lmStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))
      const lmEnd = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
      return { from: lmStart, to: lmEnd }
    }
    case '90d':
      return { from: new Date(todayUtc.getTime() - 89 * 86400000), to: tomorrowUtc }
  }
}

function inRange(iso: string, from: Date, to: Date): boolean {
  const d = new Date(iso).getTime()
  return Number.isFinite(d) && d >= from.getTime() && d < to.getTime()
}

const MONTH_FMT = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  timeZone: 'UTC',
  year: '2-digit',
})
const DAY_FMT = new Intl.DateTimeFormat('en-US', {
  day: '2-digit',
  month: 'short',
  timeZone: 'UTC',
})

function buildChartPoints(
  buckets: CostBucket[],
  workspaceIds: ReadonlySet<string>,
  from: Date,
  to: Date,
  group: GroupKey,
): SpendPoint[] {
  const filtered = buckets.filter((b) => inRange(b.starting_at, from, to))

  if (group === 'day') {
    return filtered
      .map((b) => {
        const d = new Date(b.starting_at)
        const value = bucketCostUsd(b, workspaceIds)
        return { iso: b.starting_at, label: DAY_FMT.format(d), value, isPeak: false }
      })
      .sort((a, b) => new Date(a.iso).getTime() - new Date(b.iso).getTime())
  }

  // Monthly aggregation — bucket key = YYYY-MM (UTC).
  const map = new Map<string, { value: number; iso: string }>()
  for (const b of filtered) {
    const d = new Date(b.starting_at)
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
    const monthStart = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)).toISOString()
    const prev = map.get(key) ?? { value: 0, iso: monthStart }
    map.set(key, { value: prev.value + bucketCostUsd(b, workspaceIds), iso: monthStart })
  }
  return Array.from(map.entries())
    .map(([, v]) => ({
      iso: v.iso,
      label: MONTH_FMT.format(new Date(v.iso)),
      value: v.value,
      isPeak: false,
    }))
    .sort((a, b) => new Date(a.iso).getTime() - new Date(b.iso).getTime())
}

type DescriptionRow = { description: string; total: number }

function buildDescriptionBreakdown(
  buckets: CostBucket[],
  from: Date,
  to: Date,
): DescriptionRow[] {
  const map = new Map<string, number>()
  for (const b of buckets) {
    if (!inRange(b.starting_at, from, to)) continue
    for (const r of b.results ?? []) {
      const key = r.description ?? '(unknown)'
      const amount = typeof r.amount === 'string' ? Number(r.amount) : Number(r.amount ?? 0)
      if (!Number.isFinite(amount) || amount === 0) continue
      map.set(key, (map.get(key) ?? 0) + amount)
    }
  }
  return Array.from(map.entries())
    .map(([description, total]) => ({ description, total }))
    .sort((a, b) => b.total - a.total)
}

export default function ClaudeUsageInteractive({ snap }: { snap: ClaudeUsageSnapshot }) {
  const [range, setRange] = useState<RangeKey>('7d')
  const [group, setGroup] = useState<GroupKey>('day')

  const workspaceIdSet = useMemo(() => new Set(snap.workspaceIds), [snap.workspaceIds])
  const { from, to } = useMemo(() => computeRange(range), [range])

  const filteredCost = useMemo(
    () => snap.costBuckets.filter((b) => inRange(b.starting_at, from, to)),
    [snap.costBuckets, from, to],
  )

  const filteredUsage = useMemo(
    () => snap.usageBuckets.filter((b) => inRange(b.starting_at, from, to)),
    [snap.usageBuckets, from, to],
  )

  const total = useMemo(
    () => filteredCost.reduce((s, b) => s + bucketCostUsd(b, workspaceIdSet), 0),
    [filteredCost, workspaceIdSet],
  )
  const activeDays = useMemo(
    () => filteredCost.filter((b) => bucketCostUsd(b, workspaceIdSet) > 0).length,
    [filteredCost, workspaceIdSet],
  )
  const avgDaily = activeDays > 0 ? total / activeDays : 0
  const dayCount = Math.max(1, Math.round((to.getTime() - from.getTime()) / 86400000))

  const tokens = useMemo(
    () =>
      filteredUsage.reduce(
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
      ),
    [filteredUsage],
  )

  const chartPoints = useMemo(
    () => buildChartPoints(snap.costBuckets, workspaceIdSet, from, to, group),
    [snap.costBuckets, workspaceIdSet, from, to, group],
  )

  const descriptionRows = useMemo(
    () => buildDescriptionBreakdown(snap.descriptionBuckets, from, to),
    [snap.descriptionBuckets, from, to],
  )
  const descriptionTotal = descriptionRows.reduce((s, r) => s + r.total, 0)
  const topRows = descriptionRows.slice(0, 6)

  const scopeLabel =
    snap.scope === 'workspace' && snap.workspaceName
      ? snap.workspaceName
      : snap.orgName
        ? `${snap.orgName} (org-wide)`
        : 'Organization'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div
        style={{
          alignItems: 'center',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.5rem',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Claude usage</h4>
          <span style={{ color: 'var(--theme-elevation-500)', fontSize: '0.72rem' }}>
            {scopeLabel}
          </span>
        </div>
        <div style={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
          <Select<RangeKey>
            label="Range"
            onChange={setRange}
            options={RANGE_OPTIONS}
            value={range}
          />
          <Select<GroupKey>
            label="Group"
            onChange={setGroup}
            options={GROUP_OPTIONS}
            value={group}
          />
        </div>
      </div>

      <div
        style={{
          alignItems: 'baseline',
          display: 'grid',
          gap: '1rem',
          gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
        }}
      >
        <Stat
          emphasized
          hint={RANGE_OPTIONS.find((o) => o.value === range)?.label.toLowerCase()}
          label="Spend"
          value={`$${total.toFixed(2)}`}
        />
        <Stat
          hint={`${activeDays}/${dayCount} active`}
          label="Daily avg"
          value={`$${avgDaily.toFixed(2)}`}
        />
        <Stat
          hint="input + output"
          label="Tokens"
          value={formatTokens(tokens.input + tokens.output)}
        />
        <Stat
          hint="read tokens"
          label="Cache hits"
          value={formatTokens(tokens.cacheRead)}
        />
      </div>

      <div
        style={{
          background: 'var(--theme-elevation-50)',
          borderRadius: 12,
          padding: '0.85rem 0.9rem 0.5rem',
        }}
      >
        <div
          style={{
            color: 'var(--theme-elevation-500)',
            fontSize: '0.68rem',
            letterSpacing: '0.05em',
            marginBottom: 4,
            textTransform: 'uppercase',
          }}
        >
          {group === 'day' ? 'Daily spend' : 'Monthly spend'}
        </div>
        <SpendChart avg={avgDaily} points={chartPoints} />
      </div>

      {topRows.length > 0 ? (
        <details
          style={{
            background: 'var(--theme-elevation-50)',
            borderRadius: 12,
            padding: '0.6rem 0.9rem',
          }}
        >
          <summary
            style={{
              color: 'var(--theme-elevation-600)',
              cursor: 'pointer',
              fontSize: '0.78rem',
              fontWeight: 500,
            }}
          >
            Cost by description (org-wide) · ${descriptionTotal.toFixed(2)}
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
            {topRows.map((r) => (
              <div
                key={r.description}
                style={{
                  display: 'flex',
                  fontSize: '0.74rem',
                  gap: '0.6rem',
                  justifyContent: 'space-between',
                }}
              >
                <span
                  style={{
                    color: 'var(--theme-elevation-600)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={r.description}
                >
                  {r.description}
                </span>
                <span style={{ color: 'var(--theme-text)', fontVariantNumeric: 'tabular-nums' }}>
                  ${r.total.toFixed(2)}
                </span>
              </div>
            ))}
            {descriptionRows.length > topRows.length ? (
              <div
                style={{
                  color: 'var(--theme-elevation-400)',
                  fontSize: '0.7rem',
                  marginTop: 4,
                }}
              >
                + {descriptionRows.length - topRows.length} more rows
              </div>
            ) : null}
          </div>
          <p
            style={{
              color: 'var(--theme-elevation-400)',
              fontSize: '0.68rem',
              lineHeight: 1.45,
              margin: '8px 0 0',
            }}
          >
            Anthropic&apos;s Admin API returns <em>gross</em> model cost (before Claude
            Code / Pro plan credits). The Console&apos;s &quot;Cost&quot; page shows
            net API-only billing after credits. Use this breakdown to identify which
            usage rows are covered by plan credits.
          </p>
        </details>
      ) : null}

      <span style={{ color: 'var(--theme-elevation-500)', fontSize: '0.7rem' }}>
        {activeDays > 0
          ? `${activeDays} active day${activeDays > 1 ? 's' : ''} in window · refreshes every 60s`
          : 'No spend in this window · refreshes every 60s'}
      </span>
    </div>
  )
}
