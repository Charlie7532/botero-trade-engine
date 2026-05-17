import { notFound } from 'next/navigation'
import configPromise from '@payload-config'
import { getPayload } from 'payload'

import { userSession } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'

type PageArgs = {
  params: Promise<{ slug: string }>
}

export default async function PortfolioMembersPage({ params }: PageArgs) {
  const { slug } = await params

  const { user } = await userSession()

  if (!user) return null

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  const payload = await getPayload({ config: configPromise })
  const { docs: memberships } = await payload.find({
    collection: 'portfolio-memberships',
    where: { portfolio: { equals: portfolio.id } },
    depth: 1,
    overrideAccess: false,
    user,
  })

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Members</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {portfolio.name}
        </h1>
        <p className="mt-1.5 text-sm text-muted">People with access to this portfolio.</p>
      </header>

      <section className="rounded-2xl border border-border bg-surface">
        <ul className="divide-y divide-border">
          {memberships.map((m) => {
            const member = typeof m.user === 'object' ? m.user : null
            return (
              <li key={m.id} className="flex items-center justify-between px-6 py-3">
                <div>
                  <p className="text-sm text-foreground">
                    {member && 'name' in member && member.name ? String(member.name) : '—'}
                  </p>
                  <p className="text-xs text-muted">
                    {member && 'email' in member ? String(member.email) : ''}
                  </p>
                </div>
                <span className="text-xs text-muted capitalize">{m.portfolioRole}</span>
              </li>
            )
          })}
        </ul>

        {memberships.length === 0 && (
          <p className="px-6 py-8 text-sm text-muted text-center">No members yet.</p>
        )}
      </section>
    </div>
  )
}
