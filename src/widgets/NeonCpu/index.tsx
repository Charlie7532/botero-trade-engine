import type { WidgetServerProps } from 'payload'

import { loadRecentSeries } from '@/collections/InfraSnapshots/application/useCases/loadRecentSeries'
import InfraLineChart from '@/widgets/_shared/InfraLineChart'
import InfraWidgetShell from '@/widgets/_shared/InfraWidgetShell'
import { buildSeriesReader } from '@/widgets/_shared/buildSeriesReader'
import { toRatePoints } from '@/widgets/_shared/seriesMappers'

/**
 * Neon CPU — derives vCPU usage rate from the cumulative cpu_used_sec counter
 * exposed by the Neon Console API. rate = Δsec_cpu / Δsec_wall.
 */
export default async function NeonCpuWidget({ req }: WidgetServerProps) {
  const reader = buildSeriesReader(req)
  if (!reader) {
    return (
      <InfraWidgetShell title="Neon CPU" badge="Offline">
        Database adapter offline — cannot read infra snapshots.
      </InfraWidgetShell>
    )
  }

  const rows = await loadRecentSeries(reader, ['cpu_used_sec'])
  const points = toRatePoints(rows, 'cpu_used_sec', 'vcpu')
  const last = [...points].reverse().find((p) => p.values.vcpu != null)
  const lastVcpu = last?.values.vcpu ?? null

  return (
    <InfraWidgetShell
      title="Neon CPU"
      badge={lastVcpu == null ? '—' : `${lastVcpu.toFixed(2)} vCPU`}
      badgeTitle="Latest 5-min averaged vCPU usage"
      footer="Sampled every 5 min · derived from cumulative cpu_used_sec · last 24 h"
    >
      <InfraLineChart
        points={points}
        series={[{ key: 'vcpu', label: 'vCPU used', color: '#3b82f6' }]}
        format="vcpu"
      />
    </InfraWidgetShell>
  )
}
