/** Snapshots older than this are evicted on every capture. */
export const RETENTION_DAYS = 90

/** Snapshots are captured every N minutes by the Vercel cron. */
export const CAPTURE_INTERVAL_MINUTES = 5

/** Default time window for widget series queries (24h). */
export const DEFAULT_SERIES_HOURS = 24
