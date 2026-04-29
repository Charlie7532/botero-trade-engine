import Link from 'next/link'
import { redirect } from 'next/navigation'
import type { ReactNode } from 'react'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/getUserPortfolios'

export default async function PortafolioLayout({ children }: { children: ReactNode }) {
  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  if (!user) {
    redirect('/admin/login?redirect=%2Fportafolio')
  }

  const portfolios = await getUserPortfolios(user.id)

  return (
    <main className="min-h-[calc(100vh-10rem)] bg-slate-950 text-slate-100">
      <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 px-4 py-8 md:grid-cols-[260px_minmax(0,1fr)] md:px-6">
        <aside className="h-fit rounded-xl border border-slate-800 bg-slate-900/80 p-4">
          <div className="mb-6 border-b border-slate-800 pb-4">
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-300/90">Portafolio Handle</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-100">Dashboard</h2>
            <p className="mt-1 text-sm text-slate-400">Manage your portfolios, broker links, and bot assignments.</p>
          </div>

          <nav className="space-y-2">
            <Link className="block rounded-md bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700" href="/portafolio">
              Overview
            </Link>
          </nav>

          <div className="mt-6 border-t border-slate-800 pt-4">
            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Your Portfolios</p>
            <ul className="space-y-2">
              {portfolios.map((portfolio) => (
                <li key={portfolio.id}>
                  <Link
                    className="block rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-300 hover:border-emerald-400/50 hover:bg-slate-800"
                    href={`/portafolio/${portfolio.slug}`}
                  >
                    <span className="block truncate">{portfolio.name}</span>
                    <span className="mt-1 block text-xs uppercase tracking-wide text-slate-500">
                      {portfolio.role} • {portfolio.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 md:p-6">{children}</section>
      </div>
    </main>
  )
}
