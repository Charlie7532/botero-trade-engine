'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts'

type GexBar = { strike: number; call_oi: number; put_oi: number; net: number }
type PainPoint = { strike: number; pain: number }

export function GexBarChart({
  data,
  spotPrice,
  height = 260,
}: {
  data: GexBar[]
  spotPrice: number | null
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8 }}>
        <XAxis type="number" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }} />
        <YAxis
          type="category"
          dataKey="strike"
          tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }}
          width={48}
        />
        <Tooltip
          contentStyle={{
            background: '#0f0f0f',
            border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 11,
          }}
          formatter={(v: number) => v.toLocaleString()}
        />
        <ReferenceLine x={0} stroke="rgba(255,255,255,0.3)" />
        {spotPrice !== null && (
          <ReferenceLine
            y={data.reduce((acc, d) =>
              Math.abs(d.strike - spotPrice) < Math.abs(acc.strike - spotPrice) ? d : acc,
              data[0] ?? { strike: 0, net: 0, call_oi: 0, put_oi: 0 },
            ).strike}
            stroke="#f59e0b"
            strokeDasharray="3 3"
            label={{ value: 'Spot', fill: '#f59e0b', fontSize: 10 }}
          />
        )}
        <Bar dataKey="net">
          {data.map((d, i) => (
            <Cell key={i} fill={d.net >= 0 ? '#22c55e' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function MaxPainBarChart({ data, height = 200 }: { data: PainPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 8 }}>
        <XAxis dataKey="strike" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }} />
        <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }} />
        <Tooltip
          contentStyle={{
            background: '#0f0f0f',
            border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 11,
          }}
          formatter={(v: number) => v.toLocaleString()}
        />
        <Bar dataKey="pain" fill="#6366f1" />
      </BarChart>
    </ResponsiveContainer>
  )
}
