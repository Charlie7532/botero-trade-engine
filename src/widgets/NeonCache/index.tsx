import type { WidgetServerProps } from 'payload'

import { loadRecentSeries } from '@/collections/InfraSnapshots/application/useCases/loadRecentSeries'
import InfraLineChart from '@/widgets/_shared/InfraLineChart'
import InfraWidgetShell from '@/widgets/_shared/InfraWidgetShell'
import { buildSeriesReader } from '@/widgets/_shared/buildSeriesReader'
import { toChartPoints } from '@/widgets/_shared/seriesMappers'

const GB = 1024 ** 3
const MB = 1024 ** 2

function fmtBytes(v: number): string {
  if (v >= GB) return `${(v / GB).toFixed(2)} GB`
  if (v >= MB) return `${(v / MB).toFixed(1)} MB`
  return `${v} B`
}

/**
 * Neon working data size — closest available proxy for "RAM in use" on Neon's
 * serverless tier. Plotted in GB.
 */
export default async function NeonCacheWidget({ req }: WidgetServerProps) {
  const reader = buildSeriesReader(req)
  if (!reader) {
    return (
      <InfraWidgetShell title="Neon Working Set" badge="Offline">
        Database adapter offline — cannot read infra snapshots.
      </InfraWidgetShell>
    )
  }

  const rows = await loadRecentSeries(reader, ['working_data_bytes'])
  const points = toChartPoints(rows).map((p) => ({
    ...p,
    values: { bytes: p.values.working_data_bytes ?? null },
  }))

  const last = rows[rows.length - 1]
  const lastBytes = last?.values.working_data_bytes ?? null

  return (
    <InfraWidgetShell
      title="Neon Working Set"
      badge={lastBytes == null ? '—' : fmtBytes(lastBytes)}
      badgeTitle="Closest available proxy for RAM in use"
      footer="Sampled every 5 min · working_data_bytes (Neon Console API) · last 24 h"
    >
      <InfraLineChart
        points={points}
        series={[{ key: 'bytes', label: 'Working set', color: '#3b82f6' }]}
        format="bytes"
      />
    </InfraWidgetShell>
  )
}
