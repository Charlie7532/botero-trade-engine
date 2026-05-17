import type { SeriesPoint, SeriesReader } from '../../domain/ports/SeriesReader'
import { DEFAULT_SERIES_HOURS } from '../../domain/rules/retentionRules'

/**
 * Use case: fetch the most recent infra series for a given set of columns.
 * Thin orchestration around SeriesReader — kept here so widgets depend on the
 * application layer, not on infrastructure.
 */
export async function loadRecentSeries(
  reader: SeriesReader,
  columns: readonly string[],
  hours: number = DEFAULT_SERIES_HOURS,
): Promise<SeriesPoint[]> {
  return reader.findRecent(columns, hours)
}
