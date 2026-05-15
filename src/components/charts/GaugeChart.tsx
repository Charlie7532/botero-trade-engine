'use client'

import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts'

type Props = {
  /** Score 0-100. */
  value: number
  /** Optional center label (e.g. "Greed"). */
  label?: string
  /** Color is auto-derived from value if not provided. */
  color?: string
  height?: number
}

function colorFor(score: number): string {
  if (score < 25) return '#ef4444' // extreme fear → red
  if (score < 45) return '#f97316' // fear → orange
  if (score < 55) return '#eab308' // neutral → yellow
  if (score < 75) return '#84cc16' // greed → lime
  return '#22c55e' // extreme greed → green
}

/**
 * Radial gauge from 0–100 (Fear & Greed style).
 */
export function GaugeChart({ value, label, color, height = 180 }: Props) {
  const safe = Math.max(0, Math.min(100, value))
  const fill = color ?? colorFor(safe)
  const data = [{ name: 'score', value: safe, fill }]

  return (
    <div className="relative w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          innerRadius="70%"
          outerRadius="100%"
          data={data}
          startAngle={210}
          endAngle={-30}
          barSize={14}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={6} background={{ fill: 'rgba(255,255,255,0.06)' }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-3xl font-semibold text-foreground">{Math.round(safe)}</span>
        {label && <span className="text-xs uppercase tracking-wider text-muted mt-1">{label}</span>}
      </div>
    </div>
  )
}
