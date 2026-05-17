import type { WidgetServerProps } from 'payload'

import { loadRecentSeries } from '@/collections/InfraSnapshots/application/useCases/loadRecentSeries'
import InfraLineChart from '@/widgets/_shared/InfraLineChart'
import InfraWidgetShell from '@/widgets/_shared/InfraWidgetShell'
import { buildSeriesReader } from '@/widgets/_shared/buildSeriesReader'
import { toChartPoints } from '@/widgets/_shared/seriesMappers'

const COLUMNS = ['pooler_active', 'pooler_waiting']

/**
 * Pooler client connections (PgBouncer). Neon's hosted pooler does not expose
 * SHOW POOLS, so values are typically null — the widget renders an explanation.
 */
export default async function PoolerConnectionsWidget({ req }: WidgetServerProps) {
  const reader = buildSeriesReader(req)
  if (!reader) {
    return (
      <InfraWidgetShell title="Pooler Connections" badge="Offline">
        Database adapter offline — cannot read infra snapshots.
      </InfraWidgetShell>
    )
  }

  const rows = await loadRecentSeries(reader, COLUMNS)
  const hasAny = rows.some((r) => r.values.pooler_active != null || r.values.pooler_waiting != null)

  if (!hasAny) {
    return (
      <InfraWidgetShell
        title="Pooler Connections"
        badge="Unavailable"
        badgeTitle="Neon does not expose SHOW POOLS"
        footer="Neon's hosted PgBouncer does not allow SHOW POOLS / SHOW STATS. Use a self-hosted pooler to enable this widget."
      >
        <div
          style={{
            alignItems: 'center',
            background: 'var(--theme-elevation-50)',
            borderRadius: 10,
            color: 'var(--theme-elevation-400)',
            display: 'flex',
            fontSize: '0.8rem',
            height: 160,
            justifyContent: 'center',
            padding: '0 1rem',
            textAlign: 'center',
          }}
        >
          Pooler stats are not exposed by Neon&apos;s managed PgBouncer.
        </div>
      </InfraWidgetShell>
    )
  }

  const points = toChartPoints(rows).map((p) => ({
    ...p,
    values: {
      active: p.values.pooler_active ?? null,
      waiting: p.values.pooler_waiting ?? null,
    },
  }))

  return (
    <InfraWidgetShell
      title="Pooler Connections"
      footer="Sampled every 5 min · PgBouncer SHOW POOLS · last 24 h"
    >
      <InfraLineChart
        points={points}
        series={[
          { key: 'active', label: 'Active', color: '#3b82f6' },
          { key: 'waiting', label: 'Waiting', color: '#ef4444' },
        ]}
        format="integer"
      />
    </InfraWidgetShell>
  )
}
