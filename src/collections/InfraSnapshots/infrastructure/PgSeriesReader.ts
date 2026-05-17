import type { SeriesPoint, SeriesReader } from '../domain/ports/SeriesReader'
import type { PgClient } from './PgStatProbe'

const ALLOWED = new Set([
  'cpu_used_sec',
  'compute_time_sec',
  'active_time_sec',
  'working_data_bytes',
  'data_storage_bytes_hour',
  'written_data_bytes',
  'data_transfer_bytes',
  'endpoint_state',
  'autoscale_min_cu',
  'autoscale_max_cu',
  'active_backends',
  'idle_backends',
  'idle_in_txn_backends',
  'total_backends',
  'max_connections',
  'xact_commit',
  'xact_rollback',
  'deadlocks',
  'blks_hit',
  'blks_read',
  'pooler_active',
  'pooler_waiting',
  'pooler_server_active',
  'pooler_server_idle',
])

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'bigint') return Number(v)
  if (typeof v === 'string') {
    const p = Number(v)
    return Number.isFinite(p) ? p : null
  }
  return null
}

/** Reads infra_snapshots from the bound pg pool. Whitelists column names. */
export class PgSeriesReader implements SeriesReader {
  constructor(private readonly client: PgClient) {}

  async findRecent(columns: readonly string[], hours: number): Promise<SeriesPoint[]> {
    const safe = columns.filter((c) => ALLOWED.has(c))
    if (safe.length === 0) return []
    const colsSql = ['captured_at', ...safe].map((c) => `"${c}"`).join(', ')
    const safeHours = Math.max(1, Math.min(720, Math.floor(hours)))

    try {
      const res = await this.client.query(
        `SELECT ${colsSql} FROM payload.infra_snapshots
         WHERE captured_at > NOW() - INTERVAL '${safeHours} hours'
         ORDER BY captured_at ASC`,
      )
      return res.rows.map((r) => {
        const values: Record<string, number | null> = {}
        for (const c of safe) values[c] = n(r[c])
        const ts = r.captured_at
        const iso =
          ts instanceof Date
            ? ts.toISOString()
            : typeof ts === 'string'
              ? ts
              : new Date().toISOString()
        return { capturedAt: iso, values }
      })
    } catch {
      return []
    }
  }
}
