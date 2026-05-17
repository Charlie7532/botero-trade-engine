import type { SeriesPoint } from '@/collections/InfraSnapshots/domain/ports/SeriesReader'
import type { ChartPoint } from './InfraLineChart'

const TIME_FMT = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** Format a SeriesPoint timestamp as HH:MM for the X axis. */
export function toLabel(iso: string): string {
  const d = new Date(iso)
  return Number.isFinite(d.getTime()) ? TIME_FMT.format(d) : iso
}

/** Pass-through mapper: SeriesPoint → ChartPoint with HH:MM label. */
export function toChartPoints(rows: SeriesPoint[]): ChartPoint[] {
  return rows.map((r) => ({ iso: r.capturedAt, label: toLabel(r.capturedAt), values: r.values }))
}

/**
 * Convert a cumulative counter column into per-interval rate.
 * For row i: rate_i = (value_i - value_{i-1}) / (t_i - t_{i-1} seconds)
 * The first row's rate is null. Negative deltas (counter reset) → null.
 */
export function toRatePoints(
  rows: SeriesPoint[],
  rateKey: string,
  outKey: string,
): ChartPoint[] {
  const out: ChartPoint[] = []
  for (let i = 0; i < rows.length; i += 1) {
    const cur = rows[i]
    if (!cur) continue
    const label = toLabel(cur.capturedAt)
    let rate: number | null = null
    if (i > 0) {
      const prev = rows[i - 1]
      if (prev) {
        const curV = cur.values[rateKey]
        const prevV = prev.values[rateKey]
        const dt = (new Date(cur.capturedAt).getTime() - new Date(prev.capturedAt).getTime()) / 1000
        if (curV != null && prevV != null && dt > 0 && curV >= prevV) {
          rate = (curV - prevV) / dt
        }
      }
    }
    out.push({ iso: cur.capturedAt, label, values: { [outKey]: rate } })
  }
  return out
}
