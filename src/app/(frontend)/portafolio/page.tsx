import Link from 'next/link'
import { redirect } from 'next/navigation'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/getUserPortfolios'

export default async function PortafolioIndexPage() {
  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const portfolios = await getUserPortfolios(user.id)

  if (portfolios.length === 1) {
    const [onlyPortfolio] = portfolios
    redirect(`/portafolio/${onlyPortfolio!.slug}`)
  }

  return (
    <div>
      <header className="mb-6 border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-semibold text-slate-100">Your Portfolios</h1>
        <p className="mt-1 text-sm text-slate-400">
          Choose a portfolio to open its dashboard.
        </p>
      </header>

      {portfolios.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/70 p-6 text-sm text-slate-300">
          <p>You do not have any portfolios yet.</p>
          <p className="mt-2 text-slate-400">
            Create one from the admin panel to start managing broker credentials and bot assignments.
          </p>
          <Link className="mt-4 inline-block rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400" href="/admin/collections/portfolios">
            Open Portfolios Admin
          </Link>
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {portfolios.map((portfolio) => (
            <li key={portfolio.id}>
              <Link
                className="block rounded-lg border border-slate-800 bg-slate-900/70 p-4 hover:border-emerald-400/60"
                href={`/portafolio/${portfolio.slug}`}
              >
                <h2 className="text-lg font-medium text-slate-100">{portfolio.name}</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Role: <span className="uppercase tracking-wide text-slate-300">{portfolio.role}</span>
                </p>
                <p className="text-sm text-slate-400">
                  Status: <span className="uppercase tracking-wide text-slate-300">{portfolio.status}</span>
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
