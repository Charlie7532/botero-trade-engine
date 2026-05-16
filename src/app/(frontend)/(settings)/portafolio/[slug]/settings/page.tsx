import { notFound } from 'next/navigation'

import { getServerUser } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import RenamePortfolioForm from './RenamePortfolioForm'

type PageArgs = {
  params: Promise<{ slug: string }>
}

export default async function PortfolioSettingsPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await getServerUser()

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <h2 className="mb-6 text-[11px] font-semibold tracking-widest uppercase text-muted">
        General
      </h2>
      <RenamePortfolioForm currentName={portfolio.name} portfolioId={portfolio.id} />
    </section>
  )
}
