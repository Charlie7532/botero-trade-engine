import type { ReactNode } from 'react'

import { userSession } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import SidebarUser from '@/components/Portafolio/SidebarUser'
import PortafolioNav from '@/components/Portafolio/PortafolioNav'

export default async function PortafolioLayout({ children }: { children: ReactNode }) {
  const { user } = await userSession()

  if (!user) return null

  const portfolios = await getUserPortfolios(user.id)

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden md:flex flex-col w-60 shrink-0 border-r border-border bg-surface">
        <div className="px-4 py-5 border-b border-border">
          <h2 className="text-[11px] font-semibold tracking-widest uppercase text-muted">Botero Trade</h2>
        </div>

        <PortafolioNav portfolios={portfolios} />

        <div className="border-t border-border p-2">
          <SidebarUser user={user} />
        </div>
      </aside>

      <main className="flex-1 min-w-0 overflow-y-auto">
        <section className="mx-auto max-w-7xl p-5 md:p-8">{children}</section>
      </main>
    </div>
  )
}
