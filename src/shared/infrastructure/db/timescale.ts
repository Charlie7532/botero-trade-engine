import 'server-only'

import { Pool, type PoolConfig } from 'pg'

/**
 * Single shared pg Pool against POSTGRES_URL (Neon / Vercel Postgres).
 * Reads the same TimescaleDB schema (`market.*`) that the Python Vault Daemon writes.
 *
 * Survives Next.js HMR by stashing the pool on globalThis.
 */
declare global {
  // eslint-disable-next-line no-var
  var __timescalePool: Pool | undefined
}

function makePool(): Pool {
  const connectionString = process.env.POSTGRES_URL || process.env.DATABASE_URL
  if (!connectionString) {
    throw new Error('POSTGRES_URL (or DATABASE_URL) is required for the market data store')
  }
  const config: PoolConfig = {
    connectionString,
    max: 5,
    idleTimeoutMillis: 30_000,
    // Neon requires SSL.
    ssl: connectionString.includes('sslmode=') ? undefined : { rejectUnauthorized: false },
  }
  return new Pool(config)
}

export function getPool(): Pool {
  if (!globalThis.__timescalePool) {
    globalThis.__timescalePool = makePool()
  }
  return globalThis.__timescalePool
}

// ── Domain row shapes ─────────────────────────────────────────

export type Bar = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type LinePoint = { time: string; value: number }

// ── Readers (mirror TimescaleDataStore methods) ───────────────

export async function loadBars(
  ticker: string,
  timeframe: string,
  startDays: number,
): Promise<Bar[]> {
  const { rows } = await getPool().query<{
    time: Date
    open: string
    high: string
    low: string
    close: string
    volume: string
  }>(
    `SELECT time, open, high, low, close, volume
       FROM market.ohlcv_bars
      WHERE ticker = $1 AND timeframe = $2
        AND time >= NOW() - ($3 || ' days')::interval
      ORDER BY time`,
    [ticker.toUpperCase(), timeframe, startDays],
  )
  return rows.map((r) => ({
    time: r.time.toISOString().slice(0, 10),
    open: Number(r.open),
    high: Number(r.high),
    low: Number(r.low),
    close: Number(r.close),
    volume: Number(r.volume ?? 0),
  }))
}

export async function loadLatestSnapshot<T = unknown>(
  category: string,
  ticker: string,
): Promise<T | null> {
  const { rows } = await getPool().query<{ data: T }>(
    `SELECT data FROM market.mcp_snapshots
      WHERE category = $1 AND ticker = $2
      ORDER BY time DESC LIMIT 1`,
    [category, ticker.toUpperCase()],
  )
  return rows[0]?.data ?? null
}

/**
 * Extract a numeric time-series of a JSONB field from snapshots.
 * `fieldPath` uses Postgres -> path syntax, e.g. ['VIX','close'].
 */
export async function loadIndicatorHistory(
  category: string,
  ticker: string,
  fieldPath: string[],
  days = 90,
): Promise<LinePoint[]> {
  // Build #>> '{a,b,c}' style extractor
  const pathLiteral = `{${fieldPath.join(',')}}`
  const { rows } = await getPool().query<{ d: string; v: string | null }>(
    `SELECT (time::date)::text AS d,
            (data #>> $3)::text AS v
       FROM market.mcp_snapshots
      WHERE category = $1 AND ticker = $2
        AND time >= NOW() - ($4 || ' days')::interval
      ORDER BY time`,
    [category, ticker.toUpperCase(), pathLiteral, days],
  )
  // Dedupe by date (last write wins)
  const map = new Map<string, number>()
  for (const r of rows) {
    if (r.v === null) continue
    const n = Number(r.v)
    if (!Number.isFinite(n)) continue
    map.set(r.d, n)
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, value]) => ({ time, value }))
}

/** Pre-vaulted macro series (FRED daily values). */
export async function loadMacro(name: string, days = 365): Promise<LinePoint[]> {
  const { rows } = await getPool().query<{ time: Date; value: string }>(
    `SELECT time, value FROM market.macro_data
      WHERE name = $1
        AND time >= NOW() - ($2 || ' days')::interval
      ORDER BY time`,
    [name, days],
  )
  return rows.map((r) => ({
    time: r.time.toISOString().slice(0, 10),
    value: Number(r.value),
  }))
}
