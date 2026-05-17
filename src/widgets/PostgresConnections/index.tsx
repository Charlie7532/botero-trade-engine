import type { WidgetServerProps } from 'payload'

import { loadRecentSeries } from '@/collections/InfraSnapshots/application/useCases/loadRecentSeries'
import InfraLineChart from '@/widgets/_shared/InfraLineChart'
import InfraWidgetShell from '@/widgets/_shared/InfraWidgetShell'
import { buildSeriesReader } from '@/widgets/_shared/buildSeriesReader'
import { toChartPoints } from '@/widgets/_shared/seriesMappers'

const COLUMNS = ['active_backends', 'idle_backends', 'idle_in_txn_backends', 'max_connections']

/** Postgres connection count by state vs. max_connections. */
export default async function PostgresConnectionsWidget({ req }: WidgetServerProps) {
  const reader = buildSeriesReader(req)
  if (!reader) {
    return (
      <InfraWidgetShell title="Postgres Connections" badge="Offline">
        Database adapter offline — cannot read infra snapshots.
      </InfraWidgetShell>
    )
  }

  const rows = await loadRecentSeries(reader, COLUMNS)
  const points = toChartPoints(rows).map((p) => ({
    ...p,
    values: {
      active: p.values.active_backends ?? null,
      idle: p.values.idle_backends ?? null,
      idleTx: p.values.idle_in_txn_backends ?? null,
    },
  }))

  const last = rows[rows.length - 1]
  const activeNow = last?.values.active_backends ?? null
  const maxConn = last?.values.max_connections ?? null
  const badge =
    activeNow == null || maxConn == null
      ? '—'
      : `${activeNow} / ${maxConn}`

  return (
    <InfraWidgetShell
      title="Postgres Connections"
      badge={badge}
      badgeTitle="Active backends vs. max_connections"
      footer="Sampled every 5 min · pg_stat_activity by state · last 24 h"
    >
      <InfraLineChart
        points={points}
        series={[
          { key: 'active', label: 'Active', color: '#3b82f6' },
          { key: 'idle', label: 'Idle', color: '#10b981' },
          { key: 'idleTx', label: 'Idle in tx', color: '#f59e0b' },
        ]}
        format="integer"
      />
    </InfraWidgetShell>
  )
}
