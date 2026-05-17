import type { Payload } from 'payload'

import { RETENTION_DAYS } from '../../domain/rules/retentionRules'
import type { InfraSnapshotInput } from '../../domain/entities/InfraSnapshotInput'
import type {
  NeonProbe,
  PgProbe,
  PoolerProbe,
  RetentionSweeper,
} from '../../domain/ports/InfraProbes'

export interface CaptureSnapshotDeps {
  payload: Payload
  neon: NeonProbe
  pg: PgProbe
  pooler: PoolerProbe
  sweeper: RetentionSweeper
}

export interface CaptureSnapshotResult {
  capturedAt: string
  errors: string[]
}

/**
 * Use case: probe Neon + Postgres + pooler in parallel, persist one snapshot row,
 * then sweep snapshots older than the retention window.
 */
export async function captureSnapshot(deps: CaptureSnapshotDeps): Promise<CaptureSnapshotResult> {
  const [neon, pg, pooler] = await Promise.all([
    deps.neon.read(),
    deps.pg.read(),
    deps.pooler.read(),
  ])

  const errors: string[] = []
  if (neon.error) errors.push(`neon:${neon.error}`)
  if (pg.error) errors.push(`pg:${pg.error}`)
  if (pooler.error) errors.push(`pooler:${pooler.error}`)

  const capturedAt = new Date().toISOString()
  const data: InfraSnapshotInput = {
    capturedAt,
    ...neon,
    ...pg,
    ...pooler,
    errors: errors.length ? errors.join(',') : undefined,
  }
  // The collection input does not carry `error` fields from readings.
  delete (data as unknown as Record<string, unknown>).error

  await deps.payload.create({ collection: 'infra-snapshots', data })
  await deps.sweeper.sweep(RETENTION_DAYS)

  return { capturedAt, errors }
}
