import { fetchMechanics } from '@/shared/infrastructure/trading-engine/market'
import { LightweightChart } from '@/components/charts/LightweightChart'
import { GexBarChart, MaxPainBarChart } from '@/components/charts/BarCharts'

import { Tile, TileEmpty } from './Tile'

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export async function MechanicsTab() {
  let data
  try {
    data = await fetchMechanics()
  } catch (e) {
    return (
      <div className="text-sm text-danger">
        Failed to load mechanics data: {(e as Error).message}
      </div>
    )
  }

  const { spy_gex, max_pain, market_tide } = data

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Tile
        title="SPY · GEX by Strike"
        subtitle="Open-interest gamma proxy · green = call-heavy, red = put-heavy"
        className="md:col-span-2"
      >
        {spy_gex.length === 0 ? (
          <TileEmpty message="No SPY options chain in the vault yet." />
        ) : (
          <GexBarChart
            data={spy_gex.slice(-30)}
            spotPrice={max_pain.spy?.current_price ?? null}
            height={320}
          />
        )}
      </Tile>

      <Tile title="Max Pain · SPY" subtitle={max_pain.spy?.expiration ?? 'No expiry'}>
        {!max_pain.spy ? (
          <TileEmpty message="No SPY chain vaulted." />
        ) : (
          <>
            <div className="flex items-baseline justify-between mb-2">
              <div>
                <p className="text-2xl font-semibold text-foreground">${fmt(max_pain.spy.max_pain_strike)}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted mt-1">Max Pain</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-foreground">${fmt(max_pain.spy.current_price)}</p>
                <p
                  className={`text-[11px] mt-1 ${
                    (max_pain.spy.distance_pct ?? 0) > 0 ? 'text-danger' : 'text-success'
                  }`}
                >
                  {max_pain.spy.distance_pct !== null
                    ? `${max_pain.spy.distance_pct > 0 ? '+' : ''}${fmt(max_pain.spy.distance_pct)}%`
                    : '—'}
                </p>
              </div>
            </div>
            <MaxPainBarChart data={max_pain.spy.pain_curve.slice(-25)} height={150} />
          </>
        )}
      </Tile>

      <Tile title="Max Pain · QQQ" subtitle={max_pain.qqq?.expiration ?? 'No expiry'}>
        {!max_pain.qqq ? (
          <TileEmpty message="No QQQ chain vaulted." />
        ) : (
          <>
            <div className="flex items-baseline justify-between mb-2">
              <div>
                <p className="text-2xl font-semibold text-foreground">${fmt(max_pain.qqq.max_pain_strike)}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted mt-1">Max Pain</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-foreground">${fmt(max_pain.qqq.current_price)}</p>
                <p
                  className={`text-[11px] mt-1 ${
                    (max_pain.qqq.distance_pct ?? 0) > 0 ? 'text-danger' : 'text-success'
                  }`}
                >
                  {max_pain.qqq.distance_pct !== null
                    ? `${max_pain.qqq.distance_pct > 0 ? '+' : ''}${fmt(max_pain.qqq.distance_pct)}%`
                    : '—'}
                </p>
              </div>
            </div>
            <MaxPainBarChart data={max_pain.qqq.pain_curve.slice(-25)} height={150} />
          </>
        )}
      </Tile>

      <Tile
        title="Market Tide"
        subtitle="UW net premium flow · institutional bias intraday"
        className="md:col-span-2"
      >
        {market_tide.length === 0 ? (
          <TileEmpty message="No market tide data vaulted today." />
        ) : (
          <LightweightChart
            mode="line"
            data={market_tide.map((t) => ({ time: t.time.slice(0, 10), value: t.net }))}
            height={240}
            color="#8b5cf6"
          />
        )}
      </Tile>
    </div>
  )
}
