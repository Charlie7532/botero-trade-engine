/**
 * Market dashboard data layer.
 *
 * Reads directly from the TimescaleDB schema (`market.*`) populated by the
 * Python Vault Daemon. NO dependency on the FastAPI backend — the dashboard
 * stays online even when the Python services are offline.
 *
 * Each builder is wrapped in unstable_cache (5 min) so the dashboard is cheap
 * to refresh and survives serverless cold starts.
 */
import 'server-only'

import { unstable_cache } from 'next/cache'

import {
  loadBars,
  loadIndicatorHistory,
  loadLatestSnapshot,
  type Bar,
  type LinePoint,
} from '@/shared/infrastructure/db/timescale'

const REVALIDATE = 300 // 5 min

// ════════════════════════════════════════════════════════════════
// Public types (kept identical to the previous FastAPI shapes so
// tab components don't need to change)
// ════════════════════════════════════════════════════════════════

export type OhlcvBar = Bar
export type { LinePoint }

export type PulseData = {
  spy: { bars: OhlcvBar[]; ma200: LinePoint[] }
  vix: { current: number | null; history: LinePoint[] }
  fear_greed: {
    score: number | null
    rating: string | null
    previous_close: number | null
    one_week_ago: number | null
    one_month_ago: number | null
    one_year_ago: number | null
  }
}

export type MaxPainData = {
  max_pain_strike: number
  current_price: number | null
  expiration: string | null
  distance_pct: number | null
  pain_curve: { strike: number; pain: number }[]
}

export type GexBar = { strike: number; call_oi: number; put_oi: number; net: number }

export type TidePoint = {
  time: string
  call_premium: number
  put_premium: number
  net: number
}

export type MechanicsData = {
  spy_gex: GexBar[]
  max_pain: { spy: MaxPainData | null; qqq: MaxPainData | null }
  market_tide: TidePoint[]
}

export type SectorPerf = {
  ticker: string
  name: string
  perf_1d: number | null
  perf_5d: number | null
  perf_1m: number | null
  perf_3m: number | null
  rs_short: number | null
  rs_long: number | null
}

export type RotationData = {
  sectors: SectorPerf[]
  breadth: {
    s5th: number | null
    s5tw: number | null
    tickers_counted: number | null
    history_200dma: LinePoint[]
    history_20dma: LinePoint[]
  }
}

export type EarningsEvent = {
  symbol: string | null
  date: string | null
  hour: string | null
  eps_estimate: number | null
  revenue_estimate: number | null
}

export type MacroData = {
  yield_curve: {
    y10: number | null
    y3m: number | null
    spread_10y_3m: number | null
    spread_history: LinePoint[]
  }
  indices: {
    sp500: number | null
    dxy: number | null
    gold: number | null
    oil: number | null
    skew: number | null
    vvix: number | null
  }
  earnings: EarningsEvent[]
  sentiment: Record<string, unknown>
}

// ════════════════════════════════════════════════════════════════
// Helpers
// ════════════════════════════════════════════════════════════════

function pctChange(closes: number[], days: number): number | null {
  if (closes.length < days + 1) return null
  const last = closes[closes.length - 1]
  const prev = closes[closes.length - 1 - days]
  if (last === undefined || !prev) return null
  return (last / prev - 1) * 100
}

function rolling(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]!
    if (i >= window) sum -= values[i - window]!
    if (i >= window - 1) out[i] = sum / window
  }
  return out
}

type Chain = {
  current_price?: number | string
  expiration?: string
  calls?: Array<{ strike: number; openInterest?: number }>
  puts?: Array<{ strike: number; openInterest?: number }>
}

function maxPainFromChain(chain: Chain | null): MaxPainData | null {
  if (!chain?.calls?.length || !chain?.puts?.length) return null
  const strikes = Array.from(
    new Set([...chain.calls.map((c) => c.strike), ...chain.puts.map((p) => p.strike)]),
  ).sort((a, b) => a - b)

  const curve: { strike: number; pain: number }[] = []
  for (const K of strikes) {
    let callPain = 0
    for (const c of chain.calls) {
      const oi = Number(c.openInterest ?? 0)
      callPain += Math.max(0, K - c.strike) * oi
    }
    let putPain = 0
    for (const p of chain.puts) {
      const oi = Number(p.openInterest ?? 0)
      putPain += Math.max(0, p.strike - K) * oi
    }
    curve.push({ strike: K, pain: callPain + putPain })
  }
  const min = curve.reduce((a, b) => (a.pain < b.pain ? a : b))
  const cur = chain.current_price !== undefined ? Number(chain.current_price) : null
  return {
    max_pain_strike: min.strike,
    current_price: cur,
    expiration: chain.expiration ?? null,
    distance_pct: cur ? ((cur - min.strike) / cur) * 100 : null,
    pain_curve: curve,
  }
}

function gexFromChain(chain: Chain | null): GexBar[] {
  if (!chain?.calls?.length || !chain?.puts?.length) return []
  const callBy = new Map<number, number>()
  const putBy = new Map<number, number>()
  for (const c of chain.calls) {
    callBy.set(c.strike, (callBy.get(c.strike) ?? 0) + Number(c.openInterest ?? 0))
  }
  for (const p of chain.puts) {
    putBy.set(p.strike, (putBy.get(p.strike) ?? 0) + Number(p.openInterest ?? 0))
  }
  const strikes = Array.from(new Set([...callBy.keys(), ...putBy.keys()])).sort((a, b) => a - b)
  return strikes.map((k) => {
    const call_oi = callBy.get(k) ?? 0
    const put_oi = putBy.get(k) ?? 0
    return { strike: k, call_oi, put_oi, net: call_oi - put_oi }
  })
}

const SECTOR_ETFS: Array<[string, string]> = [
  ['XLK', 'Technology'],
  ['XLF', 'Financials'],
  ['XLV', 'Health Care'],
  ['XLE', 'Energy'],
  ['XLY', 'Consumer Discretionary'],
  ['XLP', 'Consumer Staples'],
  ['XLI', 'Industrials'],
  ['XLB', 'Materials'],
  ['XLU', 'Utilities'],
  ['XLRE', 'Real Estate'],
  ['XLC', 'Communication Services'],
]

// ════════════════════════════════════════════════════════════════
// Builders
// ════════════════════════════════════════════════════════════════

async function buildPulse(): Promise<PulseData> {
  const spyBars = await loadBars('SPY', '1d', 730)

  // 200-DMA overlay (only emit dates where the window is full)
  const closes = spyBars.map((b) => b.close)
  const ma = rolling(closes, 200)
  const ma200: LinePoint[] = []
  for (let i = 0; i < spyBars.length; i++) {
    const v = ma[i]
    if (v !== null && v !== undefined) ma200.push({ time: spyBars[i]!.time, value: v })
  }

  const fred = (await loadLatestSnapshot<Record<string, unknown>>('macro/fred', 'SUMMARY')) ?? {}
  const vixObj = fred.VIX as { close?: number } | undefined
  const vixNow = typeof vixObj?.close === 'number' ? vixObj.close : null
  const vixHistory = await loadIndicatorHistory('macro/fred', 'SUMMARY', ['VIX', 'close'], 90)

  const fg =
    (await loadLatestSnapshot<{
      score?: number
      rating?: string
      previous_close?: number
      one_week_ago?: number
      one_month_ago?: number
      one_year_ago?: number
    }>('macro/fear_greed', 'MARKET')) ?? {}

  return {
    spy: { bars: spyBars, ma200 },
    vix: { current: vixNow, history: vixHistory },
    fear_greed: {
      score: fg.score ?? null,
      rating: fg.rating ?? null,
      previous_close: fg.previous_close ?? null,
      one_week_ago: fg.one_week_ago ?? null,
      one_month_ago: fg.one_month_ago ?? null,
      one_year_ago: fg.one_year_ago ?? null,
    },
  }
}

async function buildMechanics(): Promise<MechanicsData> {
  const spyChain = await loadLatestSnapshot<Chain>('yahoo/options', 'SPY')
  const qqqChain = await loadLatestSnapshot<Chain>('yahoo/options', 'QQQ')

  type RawTide = {
    timestamp?: string
    time?: string
    net_call_premium?: number | string
    net_put_premium?: number | string
  }
  const tideRaw = (await loadLatestSnapshot<RawTide[]>('flow/tide', 'MARKET')) ?? []
  const tide: TidePoint[] = []
  if (Array.isArray(tideRaw)) {
    for (const t of tideRaw) {
      const ts = t.timestamp ?? t.time
      if (!ts) continue
      const ncp = Number(t.net_call_premium ?? 0)
      const npp = Number(t.net_put_premium ?? 0)
      tide.push({
        time: String(ts),
        call_premium: ncp,
        put_premium: npp,
        net: ncp - npp,
      })
    }
  }

  return {
    spy_gex: gexFromChain(spyChain),
    max_pain: { spy: maxPainFromChain(spyChain), qqq: maxPainFromChain(qqqChain) },
    market_tide: tide,
  }
}

async function buildRotation(): Promise<RotationData> {
  const spy = await loadBars('SPY', '1d', 120)
  const spyCloses = spy.map((b) => b.close)

  const sectorRows = await Promise.all(
    SECTOR_ETFS.map(async ([ticker, name]) => {
      const df = await loadBars(ticker, '1d', 120)
      if (!df.length) return null
      const closes = df.map((b) => b.close)
      const p1 = pctChange(closes, 1)
      const p5 = pctChange(closes, 5)
      const p1m = pctChange(closes, 21)
      const p3m = pctChange(closes, 63)
      const spy5 = pctChange(spyCloses, 5)
      const spy21 = pctChange(spyCloses, 21)
      return {
        ticker,
        name,
        perf_1d: p1,
        perf_5d: p5,
        perf_1m: p1m,
        perf_3m: p3m,
        rs_short: p5 !== null && spy5 !== null ? p5 - spy5 : null,
        rs_long: p1m !== null && spy21 !== null ? p1m - spy21 : null,
      } satisfies SectorPerf
    }),
  )
  const sectors = sectorRows.filter((s): s is SectorPerf => s !== null)

  const breadth = (await loadLatestSnapshot<{
    s5th?: number
    s5tw?: number
    tickers_counted?: number
  }>('macro/breadth', 'SP500')) ?? {}

  const history200 = await loadIndicatorHistory('macro/breadth', 'SP500', ['s5th'], 90)
  const history20 = await loadIndicatorHistory('macro/breadth', 'SP500', ['s5tw'], 90)

  return {
    sectors,
    breadth: {
      s5th: breadth.s5th ?? null,
      s5tw: breadth.s5tw ?? null,
      tickers_counted: breadth.tickers_counted ?? null,
      history_200dma: history200,
      history_20dma: history20,
    },
  }
}

async function buildMacro(): Promise<MacroData> {
  const fred =
    (await loadLatestSnapshot<Record<string, { close?: number } | undefined>>(
      'macro/fred',
      'SUMMARY',
    )) ?? {}

  const closeOf = (k: string): number | null => {
    const v = fred[k]
    return typeof v?.close === 'number' ? v.close : null
  }

  const y10 = closeOf('YIELD_10Y')
  const y3m = closeOf('YIELD_3M')

  // Spread history: intersect dates from both series
  const h10 = await loadIndicatorHistory('macro/fred', 'SUMMARY', ['YIELD_10Y', 'close'], 180)
  const h3m = await loadIndicatorHistory('macro/fred', 'SUMMARY', ['YIELD_3M', 'close'], 180)
  const h3mMap = new Map(h3m.map((p) => [p.time, p.value]))
  const spreadHistory: LinePoint[] = []
  for (const p of h10) {
    const other = h3mMap.get(p.time)
    if (other !== undefined) spreadHistory.push({ time: p.time, value: p.value - other })
  }

  type RawEarnings = {
    symbol?: string
    date?: string
    hour?: string
    epsEstimate?: number
    revenueEstimate?: number
  }
  const earningsRaw =
    (await loadLatestSnapshot<RawEarnings[]>('finnhub/earnings', 'MARKET')) ?? []
  const earnings: EarningsEvent[] = (Array.isArray(earningsRaw) ? earningsRaw : [])
    .slice(0, 50)
    .map((e) => ({
      symbol: e.symbol ?? null,
      date: e.date ?? null,
      hour: e.hour ?? null,
      eps_estimate: typeof e.epsEstimate === 'number' ? e.epsEstimate : null,
      revenue_estimate: typeof e.revenueEstimate === 'number' ? e.revenueEstimate : null,
    }))

  const sentiment =
    (await loadLatestSnapshot<Record<string, unknown>>('flow/sentiment', 'MARKET')) ?? {}

  return {
    yield_curve: {
      y10,
      y3m,
      spread_10y_3m: y10 !== null && y3m !== null ? y10 - y3m : null,
      spread_history: spreadHistory,
    },
    indices: {
      sp500: closeOf('SP500'),
      dxy: closeOf('DXY'),
      gold: closeOf('GOLD'),
      oil: closeOf('OIL'),
      skew: closeOf('SKEW'),
      vvix: closeOf('VVIX'),
    },
    earnings,
    sentiment,
  }
}

// ════════════════════════════════════════════════════════════════
// Cached public API (5-min revalidation)
// ════════════════════════════════════════════════════════════════

export const fetchPulse = unstable_cache(buildPulse, ['market:pulse'], {
  revalidate: REVALIDATE,
  tags: ['market'],
})
export const fetchMechanics = unstable_cache(buildMechanics, ['market:mechanics'], {
  revalidate: REVALIDATE,
  tags: ['market'],
})
export const fetchRotation = unstable_cache(buildRotation, ['market:rotation'], {
  revalidate: REVALIDATE,
  tags: ['market'],
})
export const fetchMacro = unstable_cache(buildMacro, ['market:macro'], {
  revalidate: REVALIDATE,
  tags: ['market'],
})
