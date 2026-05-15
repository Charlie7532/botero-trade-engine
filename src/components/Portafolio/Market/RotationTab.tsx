import { fetchRotation } from '@/shared/infrastructure/trading-engine/market'
import { LightweightChart } from '@/components/charts/LightweightChart'
import { RrgScatter } from '@/components/charts/RrgScatter'

import { Tile, TileEmpty } from './Tile'

function fmt(n: number | null, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

function perfColor(n: number | null): string {
  if (n === null) return 'bg-surface-secondary text-muted'
  if (n > 1.5) return 'bg-success/30 text-success'
  if (n > 0) return 'bg-success/15 text-success'
  if (n > -1.5) return 'bg-danger/15 text-danger'
  return 'bg-danger/30 text-danger'
}

export async function RotationTab() {
  let data
  try {
    data = await fetchRotation()
  } catch (e) {
    return (
      <div className="text-sm text-danger">
        Failed to load rotation data: {(e as Error).message}
      </div>
    )
  }

  const { sectors, breadth } = data

  const rrgPoints = sectors
    .filter((s) => s.rs_short !== null && s.rs_long !== null)
    .map((s) => ({
      name: s.name,
      ticker: s.ticker,
      x: s.rs_long ?? 0,
      y: s.rs_short ?? 0,
    }))

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Tile title="Sector Heatmap" subtitle="S&P sector ETFs · % change" className="md:col-span-2">
        {sectors.length === 0 ? (
          <TileEmpty message="No sector ETF bars in vault." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted">
                  <th className="text-left font-normal py-2 pr-2">Sector</th>
                  <th className="text-right font-normal py-2 px-2">1D</th>
                  <th className="text-right font-normal py-2 px-2">5D</th>
                  <th className="text-right font-normal py-2 px-2">1M</th>
                  <th className="text-right font-normal py-2 px-2">3M</th>
                </tr>
              </thead>
              <tbody>
                {sectors.map((s) => (
                  <tr key={s.ticker} className="border-t border-border">
                    <td className="py-2 pr-2">
                      <span className="text-foreground">{s.ticker}</span>
                      <span className="text-muted ml-2">{s.name}</span>
                    </td>
                    <td className={`text-right py-1 px-2 rounded ${perfColor(s.perf_1d)}`}>{fmt(s.perf_1d)}%</td>
                    <td className={`text-right py-1 px-2 rounded ${perfColor(s.perf_5d)}`}>{fmt(s.perf_5d)}%</td>
                    <td className={`text-right py-1 px-2 rounded ${perfColor(s.perf_1m)}`}>{fmt(s.perf_1m)}%</td>
                    <td className={`text-right py-1 px-2 rounded ${perfColor(s.perf_3m)}`}>{fmt(s.perf_3m)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tile>

      <Tile
        title="Breadth"
        subtitle="% S&P 500 above moving averages"
        accessory={
          breadth.tickers_counted ? (
            <span className="text-[10px] uppercase text-muted">{breadth.tickers_counted} tickers</span>
          ) : null
        }
      >
        {breadth.s5th === null && breadth.s5tw === null ? (
          <TileEmpty message="Breadth not vaulted yet." />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <p className="text-[10px] uppercase text-muted">% &gt; 200DMA</p>
                <p className="text-2xl font-semibold text-foreground">{fmt(breadth.s5th, 1)}%</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-muted">% &gt; 20DMA</p>
                <p className="text-2xl font-semibold text-foreground">{fmt(breadth.s5tw, 1)}%</p>
              </div>
            </div>
            {breadth.history_200dma.length > 0 && (
              <LightweightChart
                mode="line"
                data={breadth.history_200dma}
                overlay={breadth.history_20dma}
                height={140}
                color="#06b6d4"
              />
            )}
          </>
        )}
      </Tile>

      <Tile
        title="Sector Rotation Graph"
        subtitle="RS vs SPY · X = 1M, Y = 1W · top-right = leading"
        className="md:col-span-3"
      >
        {rrgPoints.length === 0 ? (
          <TileEmpty message="Not enough sector data for RRG." />
        ) : (
          <RrgScatter data={rrgPoints} height={320} />
        )}
      </Tile>
    </div>
  )
}
