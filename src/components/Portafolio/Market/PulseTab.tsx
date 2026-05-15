import { fetchPulse } from '@/shared/infrastructure/trading-engine/market'
import { LightweightChart } from '@/components/charts/LightweightChart'
import { GaugeChart } from '@/components/charts/GaugeChart'

import { Tile, TileEmpty } from './Tile'

function fmt(n: number | null, digits = 2): string {
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

export async function PulseTab() {
  let data
  try {
    data = await fetchPulse()
  } catch (e) {
    return (
      <div className="text-sm text-danger">
        Failed to load pulse data: {(e as Error).message}
      </div>
    )
  }

  const { spy, vix, fear_greed } = data
  const vz = vixZone(vix.current)

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Tile
        title="SPY"
        subtitle="Daily candles · 200-DMA overlay"
        className="md:col-span-3"
        accessory={
          spy.bars.length > 0 ? (
            <span className="text-xl font-semibold text-foreground">
              ${fmt(spy.bars[spy.bars.length - 1]!.close, 2)}
            </span>
          ) : null
        }
      >
        {spy.bars.length === 0 ? (
          <TileEmpty message="No SPY bars in the vault yet — run the data daemon." />
        ) : (
          <LightweightChart
            mode="candles"
            data={spy.bars}
            overlay={spy.ma200}
            height={360}
          />
        )}
      </Tile>

      <Tile
        title="VIX"
        subtitle="Volatility index · 90d history"
        accessory={
          <div className="flex flex-col items-end">
            <span className="text-2xl font-semibold text-foreground">{fmt(vix.current, 2)}</span>
            <span className={`text-[10px] uppercase tracking-widest ${vz.color}`}>{vz.label}</span>
          </div>
        }
      >
        {vix.history.length === 0 ? (
          <TileEmpty message="No VIX history yet." />
        ) : (
          <LightweightChart
            mode="line"
            data={vix.history}
            height={180}
            color="#f59e0b"
          />
        )}
      </Tile>

      <Tile
        title="Fear & Greed"
        subtitle="CNN composite · daily"
        accessory={
          fear_greed.rating ? (
            <span className="text-[10px] uppercase tracking-widest text-muted">
              {fear_greed.rating}
            </span>
          ) : null
        }
      >
        {fear_greed.score === null ? (
          <TileEmpty message="Not vaulted yet." />
        ) : (
          <>
            <GaugeChart value={fear_greed.score} label={fear_greed.rating ?? ''} height={170} />
            <div className="grid grid-cols-3 gap-2 mt-2 text-center">
              <div>
                <p className="text-[10px] uppercase text-muted">Prev</p>
                <p className="text-sm text-foreground">{fmt(fear_greed.previous_close, 0)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-muted">1W</p>
                <p className="text-sm text-foreground">{fmt(fear_greed.one_week_ago, 0)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-muted">1M</p>
                <p className="text-sm text-foreground">{fmt(fear_greed.one_month_ago, 0)}</p>
              </div>
            </div>
          </>
        )}
      </Tile>

      <Tile title="VIX Regime" subtitle="Mechanical thresholds">
        <div className="grid grid-cols-4 gap-2 text-center text-xs">
          <Zone label="Calm" range="<15" active={vix.current !== null && vix.current < 15} color="bg-success/15 text-success" />
          <Zone label="Normal" range="15–20" active={vix.current !== null && vix.current >= 15 && vix.current < 20} color="bg-foreground/10 text-foreground" />
          <Zone label="Stressed" range="20–30" active={vix.current !== null && vix.current >= 20 && vix.current < 30} color="bg-warning/15 text-warning" />
          <Zone label="Crisis" range=">30" active={vix.current !== null && vix.current >= 30} color="bg-danger/15 text-danger" />
        </div>
        <p className="mt-3 text-xs text-muted leading-relaxed">
          Engine gates trade entries based on the active zone — Stressed and Crisis throttle position sizing.
        </p>
      </Tile>
    </div>
  )
}

function Zone({
  label,
  range,
  active,
  color,
}: {
  label: string
  range: string
  active: boolean
  color: string
}) {
  return (
    <div
      className={`rounded-lg border p-2 ${
        active ? `${color} border-current` : 'border-border text-muted'
      }`}
    >
      <p className="font-semibold">{label}</p>
      <p className="opacity-70">{range}</p>
    </div>
  )
}
