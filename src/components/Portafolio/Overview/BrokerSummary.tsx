/**
 * Overview > Broker Summary
 *
 * Single source of truth for broker accounts on this portfolio:
 *  - Lists accounts configured in Payload (no broker is ever shown unless the
 *    user actually has an account for it on this portfolio).
 *  - For each Alpaca account, fetches live equity/positions directly from the
 *    Alpaca REST API (no Python backend hop).
 *  - For Interactive Brokers accounts, renders a "pending integration" notice
 *    until the IB adapter is wired.
 */
import Link from 'next/link'
import { getPayload } from 'payload'
import config from '@payload-config'

import { fetchAlpacaPortfolio } from '@/shared/infrastructure/trading-engine/alpaca'
import type { AlpacaPortfolio } from '@/shared/infrastructure/trading-engine/alpaca'
import { Tile, TileEmpty } from '@/components/Portafolio/Market/Tile'
import NewBrokerAccountDialog from '@/components/Portafolio/Brokers/NewBrokerAccountDialog'
import type { BrokerAccount, User } from '@/payload-types'

function money(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const abs = Math.abs(n)
  const formatted =
    abs >= 1_000_000
      ? `${(n / 1_000_000).toFixed(2)}M`
      : abs >= 1_000
        ? `${(n / 1_000).toFixed(2)}K`
        : n.toFixed(2)
  return `$${formatted}`
}

function pct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function brokerLabel(t: BrokerAccount['brokerType']): string {
  return t === 'alpaca' ? 'Alpaca' : 'Interactive Brokers'
}

type Props = {
  slug: string
  portfolioId: number | string
  user: User
}

export async function BrokerSummary({ slug, portfolioId, user }: Props) {
  const payload = await getPayload({ config })

  const result = await payload.find({
    collection: 'broker-accounts',
    where: {
      and: [
        { portfolio: { equals: portfolioId } },
        { isActive: { equals: true } },
      ],
    },
    depth: 0,
    limit: 50,
    sort: '-updatedAt',
    overrideAccess: false,
    user,
  })

  const accounts = result.docs as BrokerAccount[]

  return (
    <section className="mb-8">
      <header className="mb-3 flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">
            Broker Accounts
          </p>
          <p className="mt-1 text-xs text-muted">
            {accounts.length === 0
              ? 'No accounts connected to this portfolio yet.'
              : `${accounts.length} active · live data, 60s cache`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {accounts.length > 0 && (
            <Link
              href={`/portafolio/${slug}/brokers`}
              className="text-xs text-muted hover:text-foreground transition-colors"
            >
              Manage →
            </Link>
          )}
          <NewBrokerAccountDialog portfolioSlug={slug} triggerLabel="+ Add account" />
        </div>
      </header>

      {accounts.length === 0 ? (
        <Tile title="No broker connected">
          <div className="flex flex-col items-center justify-center gap-3 py-6">
            <p className="text-sm text-muted text-center max-w-xs">
              Connect Alpaca or Interactive Brokers to see live equity, cash and
              positions for this portfolio.
            </p>
            <NewBrokerAccountDialog
              portfolioSlug={slug}
              triggerLabel="Connect a broker"
              triggerVariant="primary"
            />
          </div>
        </Tile>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {accounts.map((account) =>
            account.brokerType === 'alpaca' ? (
              <AlpacaCard key={account.id} account={account} />
            ) : (
              <PendingCard key={account.id} account={account} />
            ),
          )}
        </div>
      )}
    </section>
  )
}

async function AlpacaCard({ account }: { account: BrokerAccount }) {
  const data = await fetchAlpacaPortfolio(account)
  const env = account.environment === 'live' ? 'LIVE' : 'PAPER'

  if (!data) {
    return (
      <Tile
        title={account.name}
        subtitle={`${brokerLabel(account.brokerType)} · ${env}`}
        accessory={
          <span className="rounded-full bg-warning/10 text-warning px-2 py-0.5 text-[10px] uppercase tracking-widest">
            offline
          </span>
        }
      >
        <TileEmpty message="Could not reach Alpaca with the stored credentials." />
      </Tile>
    )
  }

  return (
    <BrokerDataCard
      title={account.name}
      subtitle={`${brokerLabel(account.brokerType)} · ${env} · ${data.positions.length} positions`}
      data={data}
    />
  )
}

function PendingCard({ account }: { account: BrokerAccount }) {
  const env = account.environment === 'live' ? 'LIVE' : 'PAPER'
  return (
    <Tile
      title={account.name}
      subtitle={`${brokerLabel(account.brokerType)} · ${env}`}
      accessory={
        <span className="rounded-full bg-surface-secondary text-muted px-2 py-0.5 text-[10px] uppercase tracking-widest">
          pending
        </span>
      }
    >
      <TileEmpty message="Interactive Brokers integration is pending. Configuration saved." />
    </Tile>
  )
}

function BrokerDataCard({
  title,
  subtitle,
  data,
}: {
  title: string
  subtitle: string
  data: AlpacaPortfolio
}) {
  const totalPnlPct =
    data.total_value > 0 ? (data.total_unrealized_pnl / data.total_value) * 100 : null
  const cashPct = data.total_value > 0 ? (data.cash / data.total_value) * 100 : null
  const positions = [...data.positions].sort((a, b) => b.market_value - a.market_value)
  const top = positions.slice(0, 5)
  const maxValue = top.reduce((m, p) => Math.max(m, Math.abs(p.market_value)), 0)

  return (
    <Tile
      title={title}
      subtitle={subtitle}
      accessory={
        <div className="flex flex-col items-end">
          <span className="text-lg font-semibold text-foreground">{money(data.total_value)}</span>
          <span
            className={`text-[10px] uppercase tracking-widest ${
              data.total_unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
            }`}
          >
            {money(data.total_unrealized_pnl)} ({pct(totalPnlPct)})
          </span>
        </div>
      }
    >
      <div className="grid grid-cols-3 gap-3 text-center">
        <Stat
          label="Cash"
          value={money(data.cash)}
          hint={cashPct === null ? '' : `${cashPct.toFixed(1)}%`}
        />
        <Stat label="Invested" value={money(data.total_market_value)} />
        <Stat
          label="Open P&L"
          value={money(data.total_unrealized_pnl)}
          tone={data.total_unrealized_pnl >= 0 ? 'success' : 'danger'}
        />
      </div>

      <div className="mt-4">
        <p className="text-[10px] uppercase tracking-widest text-muted mb-2">Top positions</p>
        {top.length === 0 ? (
          <TileEmpty message="No open positions." />
        ) : (
          <ul className="flex flex-col gap-1.5">
            {top.map((p) => {
              const widthPct = maxValue > 0 ? (Math.abs(p.market_value) / maxValue) * 100 : 0
              const pnlPct =
                p.avg_cost > 0 ? ((p.market_price - p.avg_cost) / p.avg_cost) * 100 : null
              return (
                <li key={p.symbol} className="text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{p.symbol}</span>
                    <span
                      className={`tabular-nums ${
                        p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
                      }`}
                    >
                      {money(p.market_value)} · {pct(pnlPct)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-secondary overflow-hidden">
                    <div
                      className={`h-full ${
                        p.unrealized_pnl >= 0 ? 'bg-success/60' : 'bg-danger/60'
                      }`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Tile>
  )
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'success' | 'danger'
}) {
  const toneClass =
    tone === 'success' ? 'text-success' : tone === 'danger' ? 'text-danger' : 'text-foreground'
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className={`mt-1 text-sm font-semibold ${toneClass}`}>{value}</p>
      {hint && <p className="text-[10px] text-muted">{hint}</p>}
    </div>
  )
}
