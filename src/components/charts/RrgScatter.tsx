'use client'

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
  LabelList,
} from 'recharts'

type Point = { name: string; ticker: string; x: number; y: number }

export function RrgScatter({ data, height = 320 }: { data: Point[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 16, right: 16, left: 16, bottom: 16 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.06)" />
        <XAxis
          type="number"
          dataKey="x"
          name="RS Long"
          tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }}
          label={{ value: 'RS vs SPY (1M)', position: 'bottom', fontSize: 10, fill: 'rgba(255,255,255,0.5)' }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="RS Short"
          tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }}
          label={{ value: 'RS vs SPY (1W)', angle: -90, position: 'left', fontSize: 10, fill: 'rgba(255,255,255,0.5)' }}
        />
        <ZAxis range={[60, 60]} />
        <ReferenceLine x={0} stroke="rgba(255,255,255,0.25)" />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" />
        <Tooltip
          contentStyle={{
            background: '#0f0f0f',
            border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 11,
          }}
          formatter={(v: number) => `${v.toFixed(2)}%`}
        />
        <Scatter data={data} fill="#22c55e">
          <LabelList dataKey="ticker" position="top" style={{ fontSize: 10, fill: 'rgba(255,255,255,0.8)' }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
