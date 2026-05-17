import type { WidgetServerProps } from 'payload'

import { PgSeriesReader } from '@/collections/InfraSnapshots/infrastructure/PgSeriesReader'
import type { PgClient } from '@/collections/InfraSnapshots/infrastructure/PgStatProbe'

/**
 * Builds a SeriesReader bound to the live pg pool exposed by the Payload
 * adapter. Returns null if the adapter is offline (widget should render
 * an empty state in that case).
 */
export function buildSeriesReader(req: WidgetServerProps['req']): PgSeriesReader | null {
  const drizzle = (req.payload.db as unknown as { drizzle?: { $client?: PgClient } }).drizzle
  const client = drizzle?.$client
  if (!client || typeof client.query !== 'function') return null
  return new PgSeriesReader(client)
}
