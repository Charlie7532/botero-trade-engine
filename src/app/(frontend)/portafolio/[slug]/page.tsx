import { notFound, redirect } from 'next/navigation'
import { Suspense } from 'react'

import { getServerUser } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import { MarketSummary } from '@/components/Portafolio/Overview/MarketSummary'
import { BrokerSummary } from '@/components/Portafolio/Overview/BrokerSummary'
import { AgentsList } from '@/components/Portafolio/Overview/AgentsList'
import { Tile, TileEmpty } from '@/components/Portafolio/Market/Tile'

type PageArgs = {
  params: Promise<{
    slug: string
  }>
}

function SectionSkeleton({
  title,
  hint,
  count = 4,
}: {
  title: string
  hint: string
  count?: number
}) {
  return (
    <section className="mb-8">
      <header className="mb-3">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">{title}</p>
        <p className="mt-1 text-xs text-muted">{hint}</p>
      </header>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: count }).map((_, i) => (
          <Tile key={i} title="Loading…">
            <TileEmpty message="Fetching from vault…" />
          </Tile>
        ))}
      </div>
    </section>
  )
}

export default async function PortfolioDashboardPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await getServerUser()

  const portfolios = await getUserPortfolios(user.id)

  if (portfolios.length === 0) {
    redirect('/portafolio')
  }

  const currentPortfolio = portfolios.find((portfolio) => portfolio.slug === slug)

  if (!currentPortfolio) {
    notFound()
  }

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Overview</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {currentPortfolio.name}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {currentPortfolio.role} · {currentPortfolio.status}
        </p>
      </header>

      <Suspense
        fallback={
          <SectionSkeleton title="Market Snapshot" hint="Vault-backed · refreshes every 5 min" />
        }
      >
        <MarketSummary slug={slug} />
      </Suspense>

      <Suspense
        fallback={
          <SectionSkeleton
            title="Broker Accounts"
            hint="Live positions · 60s cache"
            count={2}
          />
        }
      >
        <BrokerSummary slug={slug} portfolioId={currentPortfolio.id} user={user} />
      </Suspense>

      <Suspense
        fallback={
          <SectionSkeleton title="Agents & Strategies" hint="Deployed bots · live status" count={2} />
        }
      >
        <AgentsList slug={slug} portfolioId={currentPortfolio.id} user={user} />
      </Suspense>
    </div>
  )
}
