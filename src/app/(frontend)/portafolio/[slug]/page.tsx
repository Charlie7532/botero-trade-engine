import { notFound, redirect } from 'next/navigation'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'

type PageArgs = {
  params: Promise<{
    slug: string
  }>
}

export default async function PortfolioDashboardPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const portfolios = await getUserPortfolios(user.id)

  if (portfolios.length === 0) {
    redirect('/portafolio')
  }

  const currentPortfolio = portfolios.find((portfolio) => portfolio.slug === slug)

  if (!currentPortfolio) {
    notFound()
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-10">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Portfolio</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{currentPortfolio.name}</h1>
        <p className="mt-2 text-sm text-muted">
          {currentPortfolio.role} · {currentPortfolio.status}
        </p>
      </header>

      <div className="grid gap-px bg-border rounded-2xl overflow-hidden border border-border md:grid-cols-3">
        <section className="bg-surface p-5">
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Broker Accounts</p>
          <p className="mt-2 text-sm text-foreground leading-relaxed">Manage API credentials and connection states.</p>
        </section>

        <section className="bg-surface p-5">
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Bots</p>
          <p className="mt-2 text-sm text-foreground leading-relaxed">Review strategy deployments and activity.</p>
        </section>

        <section className="bg-surface p-5">
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Members</p>
          <p className="mt-2 text-sm text-foreground leading-relaxed">Control access levels for collaborators.</p>
        </section>
      </div>
    </div>
  )
}
