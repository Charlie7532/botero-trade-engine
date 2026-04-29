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

const shellStyle = {
  background: 'linear-gradient(145deg, rgba(27, 19, 9, 0.98), rgba(49, 30, 12, 0.95))',
  border: '1px solid rgba(255, 185, 88, 0.22)',
  borderRadius: '22px',
  boxShadow: '0 18px 48px rgba(23, 12, 4, 0.26)',
  color: '#fff4dd',
  overflow: 'hidden',
}

const metricGridStyle = {
  display: 'grid',
  gap: '0.85rem',
  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
  marginTop: '1.1rem',
}

const metricStyle = {
  background: 'rgba(255, 255, 255, 0.06)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: '16px',
  padding: '0.9rem 1rem',
}

function numberFromValue(value: number | string | undefined): number {
  if (typeof value === 'number') {
    return value
  }

  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    return Number.isFinite(parsed) ? parsed : 0
  }

  return 0
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

async function getDatabaseOverview(req: WidgetServerProps['req']): Promise<DatabaseOverview | null> {
  const adapter = req.payload.db as unknown as Partial<VercelPostgresAdapter>

  if (!adapter.pool || typeof adapter.pool.query !== 'function') {
    return null
  }

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

  if (!summary) {
    return null
  }

  return {
    tableCount: numberFromValue(summary.table_count),
    seqScans: numberFromValue(summary.seq_scans),
    idxScans: numberFromValue(summary.idx_scans),
    liveRows: numberFromValue(summary.live_rows),
    deadRows: numberFromValue(summary.dead_rows),
    databaseSize: summary.database_size,
    topTables: topTablesResult.rows.map((row) => ({
      name: row.table_name,
      seqScans: numberFromValue(row.seq_scans),
      idxScans: numberFromValue(row.idx_scans),
      liveRows: numberFromValue(row.live_rows),
      deadRows: numberFromValue(row.n_dead_tup),
    })),
  }
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <div style={metricStyle}>
      <div style={{ color: 'rgba(255, 244, 221, 0.72)', fontSize: '0.76rem', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {props.label}
      </div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, marginTop: '0.35rem' }}>{props.value}</div>
    </div>
  )
}

export default async function PostgresPerformanceWidget({ req }: WidgetServerProps) {
  const databaseOverview = await getDatabaseOverview(req)
  const processCpuSeconds = (process.cpuUsage().system + process.cpuUsage().user) / 1_000_000
  const processMemoryMb = Math.round(process.memoryUsage().rss / (1024 * 1024))
  const oneMinuteLoad = os.platform() === 'win32' ? null : os.loadavg()[0]

  if (!databaseOverview) {
    return (
      <section style={shellStyle}>
        <div style={{ padding: '1.35rem 1.4rem 1.5rem' }}>
          <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
            <div>
              <div style={{ color: '#ffcc7a', fontSize: '0.78rem', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                Postgres observability
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: '0.35rem 0 0' }}>Database metrics unavailable</h3>
            </div>
            <div style={{ background: 'rgba(255, 255, 255, 0.08)', borderRadius: '999px', fontSize: '0.78rem', padding: '0.35rem 0.7rem' }}>
              Adapter offline
            </div>
          </div>
          <p style={{ color: 'rgba(255, 244, 221, 0.76)', lineHeight: 1.55, margin: '1rem 0 0' }}>
            The dashboard could not access the active Payload Postgres pool. Check the database adapter connection and runtime database permissions.
          </p>
        </div>
      </section>
    )
  }

  const totalScans = databaseOverview.seqScans + databaseOverview.idxScans
  const indexedScanRate = totalScans === 0 ? 0 : databaseOverview.idxScans / totalScans
  const rowChurnRate = databaseOverview.liveRows === 0 ? 0 : databaseOverview.deadRows / databaseOverview.liveRows

  return (
    <section style={shellStyle}>
      <div style={{ padding: '1.35rem 1.4rem 1.5rem' }}>
        <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
          <div>
            <div style={{ color: '#ffcc7a', fontSize: '0.78rem', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
              Postgres observability
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: '0.35rem 0 0' }}>Table performance and process pressure</h3>
          </div>
          <div style={{ background: 'rgba(255, 255, 255, 0.08)', borderRadius: '999px', fontSize: '0.78rem', padding: '0.35rem 0.7rem' }}>
            Live adapter
          </div>
        </div>

        <div style={metricGridStyle}>
          <MetricCard label="Tables" value={formatNumber(databaseOverview.tableCount)} />
          <MetricCard label="Database Size" value={databaseOverview.databaseSize} />
          <MetricCard label="Indexed Scan Rate" value={formatPercent(indexedScanRate)} />
          <MetricCard label="Dead Row Ratio" value={formatPercent(rowChurnRate)} />
          <MetricCard label="Node CPU Time" value={`${processCpuSeconds.toFixed(1)}s`} />
          <MetricCard label="Node RSS" value={`${formatNumber(processMemoryMb)} MB`} />
          <MetricCard label="1m Host Load" value={oneMinuteLoad === null ? 'Unavailable' : oneMinuteLoad.toFixed(2)} />
        </div>

        <div style={{ marginTop: '1.15rem' }}>
          <div style={{ color: 'rgba(255, 244, 221, 0.72)', fontSize: '0.76rem', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Busiest tables
          </div>
          <div style={{ border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '18px', marginTop: '0.7rem', overflow: 'hidden' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr style={{ background: 'rgba(255, 255, 255, 0.05)', textAlign: 'left' }}>
                  <th style={{ padding: '0.8rem 0.95rem' }}>Table</th>
                  <th style={{ padding: '0.8rem 0.95rem' }}>Seq</th>
                  <th style={{ padding: '0.8rem 0.95rem' }}>Idx</th>
                  <th style={{ padding: '0.8rem 0.95rem' }}>Live</th>
                  <th style={{ padding: '0.8rem 0.95rem' }}>Dead</th>
                </tr>
              </thead>
              <tbody>
                {databaseOverview.topTables.map((table) => (
                  <tr key={table.name} style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
                    <td style={{ padding: '0.8rem 0.95rem' }}>{table.name}</td>
                    <td style={{ padding: '0.8rem 0.95rem' }}>{formatNumber(table.seqScans)}</td>
                    <td style={{ padding: '0.8rem 0.95rem' }}>{formatNumber(table.idxScans)}</td>
                    <td style={{ padding: '0.8rem 0.95rem' }}>{formatNumber(table.liveRows)}</td>
                    <td style={{ padding: '0.8rem 0.95rem' }}>{formatNumber(table.deadRows)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}