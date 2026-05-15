import { fetchMacro } from '@/shared/infrastructure/trading-engine/market'
import { LightweightChart } from '@/components/charts/LightweightChart'

import { Tile, TileEmpty } from './Tile'

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export async function MacroTab() {
  let data
  try {
    data = await fetchMacro()
  } catch (e) {
    return (
      <div className="text-sm text-danger">
        Failed to load macro data: {(e as Error).message}
      </div>
    )
  }

  const { yield_curve, indices, earnings, sentiment } = data

  const inverted = (yield_curve.spread_10y_3m ?? 0) < 0
  const sentimentEntries = Object.entries(sentiment).slice(0, 8)

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Tile
        title="Yield Curve"
        subtitle="10Y · 3M · spread"
        accessory={
          <span
            className={`text-[10px] uppercase tracking-widest ${
              inverted ? 'text-danger' : 'text-success'
            }`}
          >
            {inverted ? 'Inverted' : 'Normal'}
          </span>
        }
        className="md:col-span-2"
      >
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <p className="text-[10px] uppercase text-muted">10Y Treasury</p>
            <p className="text-xl font-semibold text-foreground">{fmt(yield_curve.y10)}%</p>
          </div>
          <div>
            <p className="text-[10px] uppercase text-muted">3M T-Bill</p>
            <p className="text-xl font-semibold text-foreground">{fmt(yield_curve.y3m)}%</p>
          </div>
          <div>
            <p className="text-[10px] uppercase text-muted">10Y–3M Spread</p>
            <p
              className={`text-xl font-semibold ${
                inverted ? 'text-danger' : 'text-success'
              }`}
            >
              {fmt(yield_curve.spread_10y_3m)}%
            </p>
          </div>
        </div>
        {yield_curve.spread_history.length > 0 ? (
          <LightweightChart
            mode="line"
            data={yield_curve.spread_history}
            height={180}
            color={inverted ? '#ef4444' : '#22c55e'}
          />
        ) : (
          <TileEmpty message="No spread history vaulted yet." />
        )}
      </Tile>

      <Tile title="Key Indices" subtitle="Daily close">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Idx label="S&P 500" value={indices.sp500} />
          <Idx label="DXY" value={indices.dxy} />
          <Idx label="Gold" value={indices.gold} />
          <Idx label="WTI" value={indices.oil} />
          <Idx label="SKEW" value={indices.skew} />
          <Idx label="VVIX" value={indices.vvix} />
        </div>
      </Tile>

      <Tile
        title="Earnings Calendar"
        subtitle="Next 14 days · Finnhub"
        className="md:col-span-2"
      >
        {earnings.length === 0 ? (
          <TileEmpty message="No earnings vaulted." />
        ) : (
          <div className="overflow-y-auto max-h-[360px]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface">
                <tr className="text-muted">
                  <th className="text-left font-normal py-2">Symbol</th>
                  <th className="text-left font-normal py-2">Date</th>
                  <th className="text-left font-normal py-2">Hour</th>
                  <th className="text-right font-normal py-2">EPS Est</th>
                </tr>
              </thead>
              <tbody>
                {earnings.map((e, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="py-1.5 text-foreground font-medium">{e.symbol ?? '—'}</td>
                    <td className="py-1.5 text-muted">{e.date ?? '—'}</td>
                    <td className="py-1.5 text-muted uppercase">{e.hour ?? '—'}</td>
                    <td className="py-1.5 text-right text-foreground">{fmt(e.eps_estimate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tile>

      <Tile title="News Sentiment" subtitle="FinBERT scoring · vaulted">
        {sentimentEntries.length === 0 ? (
          <TileEmpty message="No sentiment vaulted today." />
        ) : (
          <ul className="space-y-2 text-xs">
            {sentimentEntries.map(([k, v]) => (
              <li key={k} className="flex items-center justify-between border-b border-border pb-1">
                <span className="text-muted truncate mr-2">{k}</span>
                <span className="text-foreground font-mono">{String(v)}</span>
              </li>
            ))}
          </ul>
        )}
      </Tile>
    </div>
  )
}

function Idx({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <p className="text-[10px] uppercase text-muted">{label}</p>
      <p className="text-base font-semibold text-foreground">{fmt(value)}</p>
    </div>
  )
}
