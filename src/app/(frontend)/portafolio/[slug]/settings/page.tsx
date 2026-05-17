import { notFound } from 'next/navigation'

import { userSession } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import RenamePortfolioForm from './RenamePortfolioForm'

type PageArgs = {
  params: Promise<{ slug: string }>
}

export default async function PortfolioSettingsPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await userSession()

  if (!user) return null

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Settings</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {portfolio.name}
        </h1>
        <p className="mt-1.5 text-sm text-muted">Rename the portfolio or adjust its status.</p>
      </header>

      <section className="rounded-2xl border border-border bg-surface p-6">
        <h2 className="mb-6 text-[11px] font-semibold tracking-widest uppercase text-muted">
          General
        </h2>
        <RenamePortfolioForm currentName={portfolio.name} portfolioId={portfolio.id} />
      </section>
    </div>
  )
}
