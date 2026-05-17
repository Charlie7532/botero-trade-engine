import type { PgReading } from '../domain/entities/InfraSnapshotInput'
import type { PgProbe, RetentionSweeper } from '../domain/ports/InfraProbes'

export interface PgClient {
  query: (text: string) => Promise<{ rows: Record<string, unknown>[] }>
}

function n(v: unknown): number | undefined {
  if (v === null || v === undefined) return undefined
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'bigint') return Number(v)
  if (typeof v === 'string') {
    const p = Number(v)
    return Number.isFinite(p) ? p : undefined
  }
  return undefined
}

/**
 * Reads connection state and cumulative counters from pg_stat_activity
 * and pg_stat_database via the bound pg pool.
 */
export class PgStatProbe implements PgProbe {
  constructor(private readonly client: PgClient) {}

  async read(): Promise<PgReading> {
    try {
      const [actRes, dbRes, settingRes] = await Promise.all([
        this.client.query(`
          SELECT
            COUNT(*) FILTER (WHERE state = 'active')::int              AS active,
            COUNT(*) FILTER (WHERE state = 'idle')::int                AS idle,
            COUNT(*) FILTER (WHERE state = 'idle in transaction')::int AS idle_in_txn,
            COUNT(*)::int                                              AS total
          FROM pg_stat_activity
          WHERE datname = current_database()
        `),
        this.client.query(`
          SELECT
            xact_commit::bigint   AS xact_commit,
            xact_rollback::bigint AS xact_rollback,
            deadlocks::bigint     AS deadlocks,
            blks_hit::bigint      AS blks_hit,
            blks_read::bigint     AS blks_read
          FROM pg_stat_database
          WHERE datname = current_database()
        `),
        this.client.query(`SELECT current_setting('max_connections')::int AS max_connections`),
      ])
      const a = actRes.rows[0] ?? {}
      const d = dbRes.rows[0] ?? {}
      const s = settingRes.rows[0] ?? {}
      return {
        activeBackends: n(a.active),
        idleBackends: n(a.idle),
        idleInTxnBackends: n(a.idle_in_txn),
        totalBackends: n(a.total),
        maxConnections: n(s.max_connections),
        xactCommit: n(d.xact_commit),
        xactRollback: n(d.xact_rollback),
        deadlocks: n(d.deadlocks),
        blksHit: n(d.blks_hit),
        blksRead: n(d.blks_read),
      }
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'query-failed' }
    }
  }
}

/** Deletes infra_snapshots rows older than `retentionDays` from payload schema. */
export class PgRetentionSweeper implements RetentionSweeper {
  constructor(private readonly client: PgClient) {}

  async sweep(retentionDays: number): Promise<void> {
    await this.client.query(
      `DELETE FROM payload.infra_snapshots WHERE captured_at < NOW() - INTERVAL '${retentionDays} days'`,
    )
  }
}
