/** One snapshot row returned by SeriesReader. Numeric columns may be null. */
export interface SeriesPoint {
  capturedAt: string
  values: Record<string, number | null>
}

/**
 * Reads the last N hours of infra snapshots, selecting only the requested
 * numeric columns. Returns rows oldest → newest.
 */
export interface SeriesReader {
  findRecent(columns: readonly string[], hours: number): Promise<SeriesPoint[]>
}
