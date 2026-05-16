import { notFound } from 'next/navigation'
import Link from 'next/link'
import configPromise from '@payload-config'
import { getPayload } from 'payload'

import { userSession } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import NewBrokerAccountDialog from '@/components/Portafolio/Brokers/NewBrokerAccountDialog'

type PageArgs = {
  params: Promise<{ slug: string }>
}

const BROKER_LABELS: Record<string, string> = {
  alpaca: 'Alpaca',
  interactive_brokers: 'Interactive Brokers',
}

const ENV_STYLES: Record<string, string> = {
  paper: 'bg-warning/10 text-warning',
  live: 'bg-danger/10 text-danger',
}

export default async function BrokerAccountsPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await userSession()

  if (!user) return null

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  const payload = await getPayload({ config: configPromise })
  const { docs: accounts } = await payload.find({
    collection: 'broker-accounts',
    where: { portfolio: { equals: portfolio.id } },
    depth: 0,
    sort: '-updatedAt',
    overrideAccess: false,
    user,
  })

  return (
    <div>
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Broker Accounts</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{portfolio.name}</h1>
          <p className="mt-2 text-sm text-muted">
            Connected brokers and execution credentials for this portfolio.
          </p>
        </div>
        <NewBrokerAccountDialog portfolioSlug={slug} triggerLabel="New Account" />
      </header>

      {accounts.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-surface px-6 py-16 text-center">
          <p className="text-sm font-medium text-foreground">No broker accounts yet</p>
          <p className="mt-1 text-sm text-muted">
            Connect Alpaca or Interactive Brokers to start executing trades from this portfolio.
          </p>
          <div className="mt-4 flex justify-center">
            <NewBrokerAccountDialog
              portfolioSlug={slug}
              triggerLabel="Connect your first broker"
            />
          </div>
        </div>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {accounts.map((account) => {
            const env = String(account.environment ?? 'paper')
            const envClass = ENV_STYLES[env] ?? ENV_STYLES.paper
            const brokerLabel = BROKER_LABELS[String(account.brokerType)] ?? String(account.brokerType ?? '—')
            return (
              <li
                key={account.id}
                className="rounded-2xl border border-border bg-surface p-5 hover:border-foreground/20 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{account.name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {brokerLabel} · {String(account.department ?? '')}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${envClass}`}>
                    {env}
                  </span>
                </div>
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-xs text-muted">
                    {account.isActive ? 'Active' : 'Inactive'}
                  </span>
                  <Link
                    href={`/admin/collections/broker-accounts/${account.id}`}
                    className="text-xs text-muted hover:text-foreground transition-colors"
                  >
                    Configure →
                  </Link>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
