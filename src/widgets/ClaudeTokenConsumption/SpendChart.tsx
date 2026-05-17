'use client'

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts'

export type SpendPoint = {
  iso: string
  label: string
  value: number
  isPeak: boolean
}

type Props = {
  points: SpendPoint[]
  avg: number
  height?: number
}

function TooltipContent({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: SpendPoint }>
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
        padding: '4px 8px',
      }}
    >
      <div style={{ fontWeight: 600 }}>${p.value.toFixed(2)}</div>
      <div style={{ opacity: 0.6, fontSize: 11 }}>{p.label}</div>
    </div>
  )
}

export default function SpendChart({ points, height = 140 }: Props) {
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
        No spend in this period
      </div>
    )
  }

  return (
    <div style={{ height, width: '100%' }}>
      <ResponsiveContainer height="100%" width="100%">
        <BarChart data={points} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
          <XAxis
            axisLine={false}
            dataKey="label"
            tick={{ fill: 'var(--theme-elevation-500)', fontSize: 11 }}
            tickLine={false}
          />
          <Tooltip
            content={<TooltipContent />}
            cursor={{ fill: 'var(--theme-elevation-100)', opacity: 0.35 }}
          />
          <Bar
            animationDuration={500}
            dataKey="value"
            isAnimationActive
            radius={[3, 3, 0, 0]}
          >
            {points.map((p) => (
              <Cell fill="#3b82f6" key={p.iso} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

