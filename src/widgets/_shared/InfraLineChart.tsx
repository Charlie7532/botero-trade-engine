'use client'

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export type SeriesDef = {
  /** Key inside each point.values object */
  key: string
  /** Display label in the tooltip */
  label: string
  /** Stroke color */
  color: string
}

export type ChartPoint = {
  iso: string
  label: string
  values: Record<string, number | null>
}

/** Serializable formatter spec — functions can't cross the server/client boundary. */
export type ValueFormat = 'number' | 'integer' | 'vcpu' | 'bytes'

const GB = 1024 ** 3
const MB = 1024 ** 2

function formatValue(v: number, fmt: ValueFormat): string {
  switch (fmt) {
    case 'integer':
      return v.toFixed(0)
    case 'vcpu':
      return `${v.toFixed(2)} vCPU`
    case 'bytes':
      if (v >= GB) return `${(v / GB).toFixed(2)} GB`
      if (v >= MB) return `${(v / MB).toFixed(1)} MB`
      return `${v.toFixed(0)} B`
    case 'number':
    default:
      return v.toFixed(2)
  }
}

function formatAxis(v: number, fmt: ValueFormat): string {
  switch (fmt) {
    case 'integer':
      return v.toFixed(0)
    case 'vcpu':
      return v.toFixed(1)
    case 'bytes':
      if (v >= GB) return `${(v / GB).toFixed(1)}G`
      if (v >= MB) return `${(v / MB).toFixed(0)}M`
      return `${v.toFixed(0)}`
    case 'number':
    default:
      return v.toFixed(1)
  }
}

type Props = {
  points: ChartPoint[]
  series: SeriesDef[]
  height?: number
  /** Format applied to tooltip and Y-axis values. Defaults to 'number'. */
  format?: ValueFormat
}

function TooltipContent({
  active,
  payload,
  series,
  format,
}: {
  active?: boolean
  payload?: Array<{ payload: ChartPoint }>
  series: SeriesDef[]
  format: ValueFormat
}) {
  if (!active || !payload?.length) return null
  const p = payload[0]?.payload
  if (!p) return null
  return (
    <div
      style={{
        background: 'var(--theme-elevation-900)',
        border: '1px solid var(--theme-elevation-150)',
        borderRadius: 6,
        color: 'var(--theme-elevation-0)',
        fontSize: 12,
        padding: '6px 9px',
        minWidth: 140,
      }}
    >
      <div style={{ opacity: 0.6, fontSize: 11, marginBottom: 4 }}>{p.label}</div>
      {series.map((s) => {
        const v = p.values[s.key]
        return (
          <div
            key={s.key}
            style={{
              alignItems: 'center',
              display: 'flex',
              gap: 8,
              justifyContent: 'space-between',
            }}
          >
            <span style={{ alignItems: 'center', display: 'flex', gap: 6 }}>
              <span
                style={{ background: s.color, borderRadius: 2, height: 8, width: 8 }}
              />
              {s.label}
            </span>
            <span style={{ fontWeight: 600 }}>
              {v == null ? '—' : formatValue(v, format)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function InfraLineChart({
  points,
  series,
  height = 160,
  format = 'number',
}: Props) {
  if (points.length === 0) {
    return (
      <div
        style={{
          alignItems: 'center',
          background: 'var(--theme-elevation-50)',
          borderRadius: 10,
          color: 'var(--theme-elevation-400)',
          display: 'flex',
          fontSize: '0.8rem',
          height,
          justifyContent: 'center',
        }}
      >
        No samples yet — the cron has not captured data.
      </div>
    )
  }

  const fmtY = (v: number) => formatAxis(v, format)

  // Flatten values into top-level keys for Recharts dataKey lookups
  const data = points.map((p) => ({
    ...p,
    ...Object.fromEntries(series.map((s) => [s.key, p.values[s.key] ?? null])),
  }))

  return (
    <div style={{ height, width: '100%' }}>
      <ResponsiveContainer height="100%" width="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--theme-elevation-100)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            axisLine={false}
            dataKey="label"
            tick={{ fill: 'var(--theme-elevation-500)', fontSize: 10 }}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            axisLine={false}
            tick={{ fill: 'var(--theme-elevation-500)', fontSize: 10 }}
            tickFormatter={fmtY}
            tickLine={false}
            width={50}
          />
          <Tooltip
            content={<TooltipContent series={series} format={format} />}
            cursor={{ stroke: 'var(--theme-elevation-200)', strokeWidth: 1 }}
          />
          {series.map((s) => (
            <Line
              animationDuration={400}
              connectNulls
              dataKey={s.key}
              dot={false}
              isAnimationActive
              key={s.key}
              stroke={s.color}
              strokeWidth={1.8}
              type="monotone"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
