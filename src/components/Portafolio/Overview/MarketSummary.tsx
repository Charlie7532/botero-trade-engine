/**
 * Overview > Market Summary
 *
 * Compact 4-tile snapshot of the most actionable market context.
 * All data comes from the Vault (no FastAPI dependency).
 */
import Link from 'next/link'

import { fetchPulse, fetchMacro } from '@/shared/infrastructure/trading-engine/market'
import { LightweightChart } from '@/components/charts/LightweightChart'
import { GaugeChart } from '@/components/charts/GaugeChart'

import { Tile, TileEmpty } from '@/components/Portafolio/Market/Tile'

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

function vixZone(v: number | null): { label: string; color: string } {
  if (v === null) return { label: 'no data', color: 'text-muted' }
  if (v < 15) return { label: 'calm', color: 'text-success' }
  if (v < 20) return { label: 'normal', color: 'text-foreground' }
  if (v < 30) return { label: 'stressed', color: 'text-warning' }
  return { label: 'crisis', color: 'text-danger' }
}

function curveLabel(spread: number | null): { label: string; color: string } {
  if (spread === null) return { label: '—', color: 'text-muted' }
  if (spread < 0) return { label: 'inverted', color: 'text-danger' }
  if (spread < 0.5) return { label: 'flat', color: 'text-warning' }
  return { label: 'normal', color: 'text-success' }
}

type Props = { slug: string }

export async function MarketSummary({ slug }: Props) {
  const [pulseRes, macroRes] = await Promise.allSettled([fetchPulse(), fetchMacro()])
  const pulse = pulseRes.status === 'fulfilled' ? pulseRes.value : null
  const macro = macroRes.status === 'fulfilled' ? macroRes.value : null

  const spyBars = pulse?.spy.bars ?? []
  const spyLast = spyBars.length > 0 ? spyBars[spyBars.length - 1].close : null
  const spyPrev = spyBars.length > 1 ? spyBars[spyBars.length - 2].close : null
  const spyChange = spyLast !== null && spyPrev ? ((spyLast - spyPrev) / spyPrev) * 100 : null
  const recentBars = spyBars.slice(-90)

  const vix = pulse?.vix ?? { current: null, history: [] }
  const fg = pulse?.fear_greed
  const vz = vixZone(vix.current)

  const curve = macro?.yield_curve
  const cz = curveLabel(curve?.spread_10y_3m ?? null)

  return (
    <section className="mb-8">
      <header className="mb-3 flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Market Snapshot</p>
          <p className="mt-1 text-xs text-muted">Vault-backed · refreshes every 5 min</p>
        </div>
        <Link
          href={`/portafolio/${slug}/market`}
          className="text-xs text-muted hover:text-foreground transition-colors"
        >
          Open full analysis →
        </Link>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Tile
          title="SPY"
          subtitle="Last 90 sessions"
          accessory={
            spyLast === null ? null : (
              <div className="flex flex-col items-end">
                <span className="text-lg font-semibold text-foreground">${fmt(spyLast, 2)}</span>
                <span
                  className={`text-[10px] uppercase tracking-widest ${
                    spyChange === null
                      ? 'text-muted'
                      : spyChange >= 0
                        ? 'text-success'
                        : 'text-danger'
                  }`}
                >
                  {spyChange === null ? '—' : `${spyChange >= 0 ? '+' : ''}${fmt(spyChange, 2)}%`}
                </span>
              </div>
            )
          }
        >
          {recentBars.length === 0 ? (
            <TileEmpty message="No SPY bars vaulted." />
          ) : (
            <LightweightChart mode="candles" data={recentBars} height={150} />
          )}
        </Tile>

        <Tile
          title="VIX"
          subtitle="Volatility regime"
          accessory={
            <div className="flex flex-col items-end">
              <span className="text-lg font-semibold text-foreground">{fmt(vix.current, 2)}</span>
              <span className={`text-[10px] uppercase tracking-widest ${vz.color}`}>{vz.label}</span>
            </div>
          }
        >
          {vix.history.length === 0 ? (
            <TileEmpty message="No VIX history." />
          ) : (
            <LightweightChart mode="line" data={vix.history} height={150} color="#f59e0b" />
          )}
        </Tile>

        <Tile
          title="Fear & Greed"
          subtitle="CNN composite"
          accessory={
            fg?.rating ? (
              <span className="text-[10px] uppercase tracking-widest text-muted">{fg.rating}</span>
            ) : null
          }
        >
          {!fg || fg.score === null ? (
            <TileEmpty message="Not vaulted yet." />
          ) : (
            <GaugeChart value={fg.score} label={fg.rating ?? ''} height={150} />
          )}
        </Tile>

        <Tile
          title="Yield Curve"
          subtitle="10Y − 3M spread"
          accessory={
            <div className="flex flex-col items-end">
              <span className="text-lg font-semibold text-foreground">
                {fmt(curve?.spread_10y_3m ?? null, 2)}%
              </span>
              <span className={`text-[10px] uppercase tracking-widest ${cz.color}`}>{cz.label}</span>
            </div>
          }
        >
          {!curve || curve.spread_history.length === 0 ? (
            <TileEmpty message="No yield-curve history." />
          ) : (
            <LightweightChart
              mode="line"
              data={curve.spread_history}
              height={150}
              color={(curve.spread_10y_3m ?? 0) < 0 ? '#ef4444' : '#22c55e'}
            />
          )}
        </Tile>
      </div>
    </section>
  )
}
