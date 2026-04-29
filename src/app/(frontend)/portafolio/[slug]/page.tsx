import { notFound, redirect } from 'next/navigation'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/getUserPortfolios'

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
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <p className="text-xs uppercase tracking-[0.2em] text-emerald-300/90">Portfolio Dashboard</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-100">{currentPortfolio.name}</h1>
        <p className="mt-1 text-sm text-slate-400">Role: {currentPortfolio.role} • Status: {currentPortfolio.status}</p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <section className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm uppercase tracking-[0.16em] text-slate-400">Broker Accounts</h2>
          <p className="mt-2 text-sm text-slate-300">Manage API credentials and connection states for this portfolio.</p>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm uppercase tracking-[0.16em] text-slate-400">Bots</h2>
          <p className="mt-2 text-sm text-slate-300">Review strategy deployments and activity linked to this portfolio.</p>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
          <h2 className="text-sm uppercase tracking-[0.16em] text-slate-400">Members</h2>
          <p className="mt-2 text-sm text-slate-300">Control access levels for collaborators and operators.</p>
        </section>
      </div>
    </div>
  )
}
