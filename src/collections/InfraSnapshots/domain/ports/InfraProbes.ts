import type { NeonReading, PgReading, PoolerReading } from '../entities/InfraSnapshotInput'

/** Reads aggregate counters and endpoint state from the Neon Console API. */
export interface NeonProbe {
  read(): Promise<NeonReading>
}

/** Reads pg_stat_activity / pg_stat_database from the bound Postgres connection. */
export interface PgProbe {
  read(): Promise<PgReading>
}

/** Reads PgBouncer admin stats. Returns error if the pooler is admin-locked (Neon). */
export interface PoolerProbe {
  read(): Promise<PoolerReading>
}

/** Deletes snapshots older than the retention window. */
export interface RetentionSweeper {
  sweep(retentionDays: number): Promise<void>
}
