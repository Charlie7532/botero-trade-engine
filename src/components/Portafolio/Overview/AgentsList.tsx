/**
 * Overview > Agents & Strategies list
 *
 * Compact mirror of the full /agents page so the user can see deployed bots
 * and create new ones from the overview.
 */
import Link from 'next/link'
import configPromise from '@payload-config'
import { getPayload } from 'payload'
import type { User } from '@/payload-types'

import { Tile } from '@/components/Portafolio/Market/Tile'
import NewAgentDialog from '@/components/Portafolio/Agents/NewAgentDialog'

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-success/10 text-success',
  stopped: 'bg-surface-secondary text-muted',
  paused: 'bg-warning/10 text-warning',
  error: 'bg-danger/10 text-danger',
}

type Props = {
  slug: string
  portfolioId: string | number
  user: User
}

export async function AgentsList({ slug, portfolioId, user }: Props) {
  const payload = await getPayload({ config: configPromise })
  const { docs: bots, totalDocs } = await payload.find({
    collection: 'bots',
    where: { portfolio: { equals: portfolioId } },
    depth: 0,
    limit: 4,
    sort: '-updatedAt',
    overrideAccess: false,
    user,
  })

  const running = bots.filter((b) => String(b.status) === 'running').length

  return (
    <Tile
      title="Agents & Strategies"
      subtitle={`${totalDocs} total · ${running} running`}
      accessory={
        <div className="flex items-center gap-2">
          <Link
            href={`/portafolio/${slug}/agents`}
            className="text-xs text-muted hover:text-foreground transition-colors"
          >
            View all →
          </Link>
          <NewAgentDialog portfolioSlug={slug} triggerLabel="+ Add" />
        </div>
      }
    >
      {bots.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm text-foreground">No agents yet</p>
          <p className="mt-1 text-xs text-muted">Deploy a Claude agent or strategy bot.</p>
          <div className="mt-3 flex justify-center">
            <NewAgentDialog portfolioSlug={slug} triggerLabel="Create one" />
          </div>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {bots.map((bot) => {
            const status = String(bot.status ?? 'stopped')
            const statusClass = STATUS_STYLES[status] ?? STATUS_STYLES.stopped
            const href = bot.botSlug
              ? `/agent/${bot.botSlug}`
              : `/admin/collections/bots/${bot.id}`
            return (
              <li
                key={bot.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-secondary/50 px-3 py-2"
              >
                <Link href={href} className="flex-1 min-w-0">
                  <p className="truncate text-sm font-medium text-foreground hover:text-foreground">
                    {bot.name}
                  </p>
                  <p className="text-[11px] text-muted">
                    {String(bot.executionType ?? '')} · {String(bot.strategyType ?? '')}
                  </p>
                </Link>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${statusClass}`}
                >
                  {status}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Tile>
  )
}
