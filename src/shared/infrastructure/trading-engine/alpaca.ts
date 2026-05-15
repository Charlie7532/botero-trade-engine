/**
 * Direct Alpaca REST adapter (server-side only).
 *
 * Uses per-portfolio encrypted credentials stored on `broker-accounts` and
 * decrypted in process. Replaces the old FastAPI hop for the overview tile.
 */
import 'server-only'

import { unstable_cache } from 'next/cache'

import { decryptValue } from '@/shared/domain/encryption'
import type { BrokerAccount } from '@/payload-types'

const TIMEOUT_MS = 4500

const PAPER_BASE = 'https://paper-api.alpaca.markets'
const LIVE_BASE = 'https://api.alpaca.markets'

export type AlpacaPosition = {
  symbol: string
  quantity: number
  avg_cost: number
  market_price: number
  market_value: number
  unrealized_pnl: number
}

export type AlpacaPortfolio = {
  accountId: number | string
  name: string
  environment: 'paper' | 'live'
  cash: number
  total_market_value: number
  total_value: number
  total_unrealized_pnl: number
  positions: AlpacaPosition[]
}

function resolveSecret(): string {
  return process.env.BROKER_CREDENTIAL_ENCRYPTION_KEY || process.env.PAYLOAD_SECRET || ''
}

function decryptCreds(account: BrokerAccount): { key: string; secret: string } | null {
  const secret = resolveSecret()
  if (!secret) return null
  if (
    !account.apiKeyEncrypted ||
    !account.apiKeyIv ||
    !account.apiKeyAuthTag ||
    !account.secretKeyEncrypted ||
    !account.secretKeyIv ||
    !account.secretKeyAuthTag
  ) {
    return null
  }
  try {
    const key = decryptValue(
      {
        ciphertext: account.apiKeyEncrypted,
        iv: account.apiKeyIv,
        authTag: account.apiKeyAuthTag,
      },
      secret,
    )
    const secretKey = decryptValue(
      {
        ciphertext: account.secretKeyEncrypted,
        iv: account.secretKeyIv,
        authTag: account.secretKeyAuthTag,
      },
      secret,
    )
    return { key, secret: secretKey }
  } catch {
    return null
  }
}

async function alpacaGet<T>(baseUrl: string, path: string, key: string, secret: string): Promise<T | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(`${baseUrl}${path}`, {
      headers: {
        'APCA-API-KEY-ID': key,
        'APCA-API-SECRET-KEY': secret,
        Accept: 'application/json',
      },
      signal: ctrl.signal,
      cache: 'no-store',
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

type AlpacaAccountResp = {
  cash: string
  portfolio_value: string
  equity: string
  long_market_value: string
  short_market_value: string
}

type AlpacaPositionResp = {
  symbol: string
  qty: string
  avg_entry_price: string
  current_price: string
  market_value: string
  unrealized_pl: string
}

function num(v: string | number | null | undefined, fallback = 0): number {
  if (v === null || v === undefined) return fallback
  const n = typeof v === 'number' ? v : parseFloat(v)
  return Number.isFinite(n) ? n : fallback
}

async function fetchAlpacaPortfolioRaw(
  accountId: number | string,
  name: string,
  environment: 'paper' | 'live',
  baseUrl: string,
  key: string,
  secret: string,
): Promise<AlpacaPortfolio | null> {
  const [account, positions] = await Promise.all([
    alpacaGet<AlpacaAccountResp>(baseUrl, '/v2/account', key, secret),
    alpacaGet<AlpacaPositionResp[]>(baseUrl, '/v2/positions', key, secret),
  ])

  if (!account) return null

  const mappedPositions: AlpacaPosition[] = (positions ?? []).map((p) => ({
    symbol: p.symbol,
    quantity: num(p.qty),
    avg_cost: num(p.avg_entry_price),
    market_price: num(p.current_price),
    market_value: num(p.market_value),
    unrealized_pnl: num(p.unrealized_pl),
  }))

  const longValue = num(account.long_market_value)
  const shortValue = num(account.short_market_value)
  const totalMarketValue = longValue + shortValue
  const totalUnrealized = mappedPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0)

  return {
    accountId,
    name,
    environment,
    cash: num(account.cash),
    total_market_value: totalMarketValue,
    total_value: num(account.portfolio_value) || num(account.equity),
    total_unrealized_pnl: totalUnrealized,
    positions: mappedPositions,
  }
}

/**
 * Fetch a single Alpaca account's live portfolio. Returns null on any failure.
 * 60-second cache keyed by account id + environment.
 */
export async function fetchAlpacaPortfolio(account: BrokerAccount): Promise<AlpacaPortfolio | null> {
  if (account.brokerType !== 'alpaca') return null

  const creds = decryptCreds(account)
  if (!creds) return null

  const environment: 'paper' | 'live' = account.environment === 'live' ? 'live' : 'paper'
  const baseUrl =
    account.alpacaBaseUrl?.trim() || (environment === 'live' ? LIVE_BASE : PAPER_BASE)

  const cached = unstable_cache(
    async () =>
      fetchAlpacaPortfolioRaw(
        account.id,
        account.name,
        environment,
        baseUrl,
        creds.key,
        creds.secret,
      ),
    ['alpaca:portfolio', String(account.id), environment],
    { revalidate: 60, tags: ['broker', `broker:${account.id}`] },
  )

  return cached()
}
