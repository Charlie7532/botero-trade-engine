import { notFound } from 'next/navigation'
import Link from 'next/link'
import configPromise from '@payload-config'
import { getPayload } from 'payload'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import NewAgentDialog from '@/components/Portafolio/Agents/NewAgentDialog'

type PageArgs = {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ type?: string }>
}

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-success/10 text-success',
  stopped: 'bg-surface-secondary text-muted',
  paused: 'bg-warning/10 text-warning',
  error: 'bg-danger/10 text-danger',
}

const TYPE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'agent', label: 'AI Agents' },
  { key: 'strategy', label: 'Strategies' },
] as const

export default async function AgentsPage({ params, searchParams }: PageArgs) {
  const { slug } = await params
  const { type } = await searchParams
  const activeFilter = type === 'agent' || type === 'strategy' ? type : 'all'

  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  const payload = await getPayload({ config: configPromise })
  const where: Record<string, unknown> = { portfolio: { equals: portfolio.id } }
  if (activeFilter !== 'all') {
    where.executionType = { equals: activeFilter }
  }
  const { docs: bots } = await payload.find({
    collection: 'bots',
    where: where as Parameters<typeof payload.find>[0]['where'],
    depth: 0,
    sort: '-updatedAt',
    overrideAccess: false,
    user,
  })

  return (
    <div>
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Agents &amp; Strategies</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{portfolio.name}</h1>
          <p className="mt-2 text-sm text-muted">
            Claude-powered agents and deterministic strategy bots deployed on this portfolio.
          </p>
        </div>
        <NewAgentDialog portfolioSlug={slug} triggerLabel="New" />
      </header>

      <div className="mb-6 flex items-center gap-1.5">
        {TYPE_FILTERS.map((f) => {
          const isActive = activeFilter === f.key
          const href = f.key === 'all' ? `/portafolio/${slug}/agents` : `/portafolio/${slug}/agents?type=${f.key}`
          return (
            <Link
              key={f.key}
              href={href}
              className={[
                'rounded-full border px-3 py-1 text-xs transition-colors',
                isActive
                  ? 'border-foreground/40 bg-surface-secondary text-foreground'
                  : 'border-border bg-surface text-muted hover:text-foreground',
              ].join(' ')}
            >
              {f.label}
            </Link>
          )
        })}
      </div>

      {bots.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-surface px-6 py-16 text-center">
          <p className="text-sm font-medium text-foreground">
            {activeFilter === 'all'
              ? 'Nothing here yet'
              : activeFilter === 'agent'
                ? 'No AI agents yet'
                : 'No strategies yet'}
          </p>
          <p className="mt-1 text-sm text-muted">
            Deploy a Claude agent or strategy bot to start trading from this portfolio.
          </p>
          <div className="mt-4 flex justify-center">
            <NewAgentDialog portfolioSlug={slug} triggerLabel="Create one" />
          </div>
        </div>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {bots.map((bot) => {
            const status = String(bot.status ?? 'stopped')
            const statusClass = STATUS_STYLES[status] ?? STATUS_STYLES.stopped
            return (
              <li
                key={bot.id}
                className="rounded-2xl border border-border bg-surface p-5 hover:border-foreground/20 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{bot.name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {String(bot.executionType ?? '')} · {String(bot.strategyType ?? '')}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${statusClass}`}>
                    {status}
                  </span>
                </div>
                {bot.description ? (
                  <p className="mt-3 line-clamp-2 text-sm text-muted">{bot.description}</p>
                ) : null}
                <div className="mt-4 flex items-center gap-3">
                  {bot.botSlug ? (
                    <Link
                      href={`/agent/${bot.botSlug}`}
                      className="text-xs text-muted hover:text-foreground transition-colors"
                    >
                      Open →
                    </Link>
                  ) : null}
                  <Link
                    href={`/admin/collections/bots/${bot.id}`}
                    className="text-xs text-muted hover:text-foreground transition-colors"
                  >
                    Configure
                  </Link>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
