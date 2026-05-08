import Link from 'next/link'
import { redirect } from 'next/navigation'
import type { ReactNode } from 'react'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'

export default async function PortafolioLayout({ children }: { children: ReactNode }) {
  const { user } = await getMeUser()

  if (!user) {
    redirect('/login?redirect=%2Fportafolio')
  }

  const portfolios = await getUserPortfolios(user.id)

  return (
    <main className="min-h-screen">
      <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 px-4 py-10 md:grid-cols-[240px_minmax(0,1fr)] md:px-6">
        <aside className="h-fit rounded-2xl border border-border bg-surface p-4">
          <div className="mb-5 border-b border-border pb-4">
            <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Botero Trade</p>
            <h2 className="mt-1.5 text-base font-semibold text-foreground">Dashboard</h2>
          </div>

          <nav>
            <Link
              className="flex items-center rounded-lg px-3 py-2 text-sm font-medium text-foreground bg-surface-secondary hover:bg-surface-tertiary transition-colors"
              href="/portafolio"
            >
              Overview
            </Link>
          </nav>

          {portfolios.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <p className="mb-2 text-[11px] font-semibold tracking-widest uppercase text-muted">Portfolios</p>
              <ul className="space-y-1">
                {portfolios.map((portfolio) => (
                  <li key={portfolio.id}>
                    <Link
                      className="flex items-center justify-between rounded-lg px-3 py-2 text-sm text-foreground hover:bg-surface-secondary transition-colors"
                      href={`/portafolio/${portfolio.slug}`}
                    >
                      <span className="truncate">{portfolio.name}</span>
                      <span className="ml-2 shrink-0 text-xs text-muted">{portfolio.role}</span>
                    </Link>
                    <Link
                      className="flex items-center rounded-lg px-3 py-1.5 text-xs text-muted hover:bg-surface-secondary transition-colors"
                      href={`/portafolio/${portfolio.slug}/settings`}
                    >
                      Settings
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>

        <section className="rounded-2xl border border-border bg-surface p-5 md:p-8">{children}</section>
      </div>
    </main>
  )
}
