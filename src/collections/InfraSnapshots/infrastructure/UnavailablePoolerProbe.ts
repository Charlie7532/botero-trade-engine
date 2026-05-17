import type { PoolerReading } from '../domain/entities/InfraSnapshotInput'
import type { PoolerProbe } from '../domain/ports/InfraProbes'

/**
 * Neon's hosted PgBouncer does NOT expose the standard PgBouncer admin console.
 * Connecting to the `pgbouncer` virtual database and issuing `SHOW POOLS` or
 * `SHOW CLIENTS` returns "ERROR: unsupported pgbouncer command".
 *
 * This adapter is kept as a port so a real PgBouncer (self-hosted, or a future
 * Neon feature) can be swapped in. For now it always reports unavailable.
 */
export class UnavailablePoolerProbe implements PoolerProbe {
  // eslint-disable-next-line @typescript-eslint/require-await
  async read(): Promise<PoolerReading> {
    return { error: 'admin-unavailable' }
  }
}
