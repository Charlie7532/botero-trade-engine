import type { VercelPostgresAdapter } from '@payloadcms/db-vercel-postgres'
import type { WidgetServerProps } from 'payload'
import os from 'os'

type DatabaseOverview = {
  databaseSize: string
  deadRows: number
  idxScans: number
  liveRows: number
  seqScans: number
  tableCount: number
  topTables: Array<{
    deadRows: number
    idxScans: number
    liveRows: number
    name: string
    seqScans: number
  }>
}

function num(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const p = Number.parseInt(v, 10)
    return Number.isFinite(p) ? p : 0
  }
  return 0
}

function fmt(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

async function getDatabaseOverview(req: WidgetServerProps['req']): Promise<DatabaseOverview | null> {
  const adapter = req.payload.db as unknown as Partial<VercelPostgresAdapter>
  if (!adapter.pool || typeof adapter.pool.query !== 'function') return null

  const summaryResult = await adapter.pool.query<{
    database_size: string
    dead_rows: number | string
    idx_scans: number | string
    live_rows: number | string
    seq_scans: number | string
    table_count: number | string
  }>(`
    SELECT
      COUNT(*)::int AS table_count,
      COALESCE(SUM(seq_scan), 0)::bigint AS seq_scans,
      COALESCE(SUM(idx_scan), 0)::bigint AS idx_scans,
      COALESCE(SUM(n_live_tup), 0)::bigint AS live_rows,
      COALESCE(SUM(n_dead_tup), 0)::bigint AS dead_rows,
      COALESCE(pg_size_pretty(SUM(pg_total_relation_size(relid))::bigint), '0 bytes') AS database_size
    FROM pg_stat_user_tables
  `)

  const topTablesResult = await adapter.pool.query<{
    idx_scans: number | string
    live_rows: number | string
    n_dead_tup: number | string
    seq_scans: number | string
    table_name: string
  }>(`
    SELECT
      relname AS table_name,
      seq_scan::bigint AS seq_scans,
      idx_scan::bigint AS idx_scans,
      n_live_tup::bigint AS live_rows,
      n_dead_tup::bigint AS n_dead_tup
    FROM pg_stat_user_tables
    ORDER BY (seq_scan + idx_scan) DESC, relname ASC
    LIMIT 5
  `)

  const summary = summaryResult.rows[0]
  if (!summary) return null

  return {
    tableCount: num(summary.table_count),
    seqScans: num(summary.seq_scans),
    idxScans: num(summary.idx_scans),
    liveRows: num(summary.live_rows),
    deadRows: num(summary.dead_rows),
    databaseSize: summary.database_size,
    topTables: topTablesResult.rows.map((row) => ({
      name: row.table_name,
      seqScans: num(row.seq_scans),
      idxScans: num(row.idx_scans),
      liveRows: num(row.live_rows),
      deadRows: num(row.n_dead_tup),
    })),
  }
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'var(--theme-elevation-50)',
        borderRadius: '8px',
        padding: '0.75rem 0.85rem',
      }}
    >
      <div style={{ color: 'var(--theme-elevation-500)', fontSize: '0.7rem', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.15rem', fontWeight: 600, marginTop: '0.2rem' }}>
        {value}
      </div>
    </div>
  )
}

const cellStyle = { fontSize: '0.82rem', padding: '0.55rem 0.7rem' }
const headerCellStyle = {
  ...cellStyle,
  color: 'var(--theme-elevation-500)',
  fontSize: '0.7rem',
  fontWeight: 600 as const,
  letterSpacing: '0.04em',
  textTransform: 'uppercase' as const,
}

export default async function PostgresPerformanceWidget({ req }: WidgetServerProps) {
  const db = await getDatabaseOverview(req)
  const cpuSec = (process.cpuUsage().system + process.cpuUsage().user) / 1_000_000
  const rssMb = Math.round(process.memoryUsage().rss / (1024 * 1024))
  const load1m = os.platform() === 'win32' ? null : os.loadavg()[0]

  if (!db) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Database unavailable</h4>
          <span
            style={{
              background: 'var(--theme-elevation-100)',
              borderRadius: '4px',
              color: 'var(--theme-elevation-500)',
              fontSize: '0.7rem',
              padding: '0.2rem 0.5rem',
            }}
          >
            Adapter offline
          </span>
        </div>
        <p style={{ color: 'var(--theme-elevation-500)', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
          Could not reach the Postgres pool. Check database connection and runtime permissions.
        </p>
      </div>
    )
  }

  const totalScans = db.seqScans + db.idxScans
  const indexedRate = totalScans === 0 ? 0 : db.idxScans / totalScans
  const churnRate = db.liveRows === 0 ? 0 : db.deadRows / db.liveRows

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0 }}>Postgres performance</h4>
        <span
          style={{
            background: 'var(--theme-elevation-100)',
            borderRadius: '4px',
            color: 'var(--theme-elevation-500)',
            fontSize: '0.7rem',
            padding: '0.2rem 0.5rem',
          }}
        >
          Live
        </span>
      </div>

      <div style={{ display: 'grid', gap: '0.5rem', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
        <Metric label="Tables" value={fmt(db.tableCount)} />
        <Metric label="DB Size" value={db.databaseSize} />
        <Metric label="Idx Scan Rate" value={pct(indexedRate)} />
        <Metric label="Dead Row %" value={pct(churnRate)} />
        <Metric label="CPU Time" value={`${cpuSec.toFixed(1)}s`} />
        <Metric label="RSS" value={`${fmt(rssMb)} MB`} />
        <Metric label="1m Load" value={load1m == null ? 'N/A' : load1m.toFixed(2)} />
      </div>

      {db.topTables.length > 0 && (
        <div>
          <div style={{ color: 'var(--theme-elevation-500)', fontSize: '0.7rem', letterSpacing: '0.04em', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
            Busiest tables
          </div>
          <div style={{ border: '1px solid var(--theme-elevation-100)', borderRadius: '8px', overflow: 'hidden' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr style={{ background: 'var(--theme-elevation-50)' }}>
                  <th style={{ ...headerCellStyle, textAlign: 'left' }}>Table</th>
                  <th style={headerCellStyle}>Seq</th>
                  <th style={headerCellStyle}>Idx</th>
                  <th style={headerCellStyle}>Live</th>
                  <th style={headerCellStyle}>Dead</th>
                </tr>
              </thead>
              <tbody>
                {db.topTables.map((t) => (
                  <tr key={t.name} style={{ borderTop: '1px solid var(--theme-elevation-100)' }}>
                    <td style={{ ...cellStyle, fontWeight: 500 }}>{t.name}</td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>{fmt(t.seqScans)}</td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>{fmt(t.idxScans)}</td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>{fmt(t.liveRows)}</td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>{fmt(t.deadRows)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}