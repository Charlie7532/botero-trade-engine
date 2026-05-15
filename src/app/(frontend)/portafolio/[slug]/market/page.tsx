import { notFound } from 'next/navigation'
import Link from 'next/link'

import { getMeUser } from '@/utilities/getMeUser'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'
import { PulseTab } from '@/components/Portafolio/Market/PulseTab'
import { MechanicsTab } from '@/components/Portafolio/Market/MechanicsTab'
import { RotationTab } from '@/components/Portafolio/Market/RotationTab'
import { MacroTab } from '@/components/Portafolio/Market/MacroTab'

type PageArgs = {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ tab?: string }>
}

const TABS = [
  { key: 'pulse', label: 'Pulse', hint: 'SPY · VIX · Fear & Greed' },
  { key: 'mechanics', label: 'Mechanics', hint: 'GEX · Max Pain · Tide' },
  { key: 'rotation', label: 'Rotation', hint: 'Sectors · Breadth · RRG' },
  { key: 'macro', label: 'Macro & Catalysts', hint: 'Yield curve · Earnings' },
] as const

type TabKey = (typeof TABS)[number]['key']

export default async function MarketAnalysisPage({ params, searchParams }: PageArgs) {
  const { slug } = await params
  const { tab } = await searchParams

  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)
  if (!portfolio) notFound()

  const active: TabKey = TABS.find((t) => t.key === tab)?.key ?? 'pulse'

  return (
    <div>
      <header className="mb-6">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Market Analysis</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{portfolio.name}</h1>
        <p className="mt-2 text-sm text-muted">
          Macro regime, dealer mechanics, sector rotation and catalysts — all sourced from the Neon Vault.
        </p>
      </header>

      <nav className="flex flex-wrap gap-2 mb-6 border-b border-border pb-3">
        {TABS.map((t) => {
          const isActive = t.key === active
          const href =
            t.key === 'pulse'
              ? `/portafolio/${slug}/market`
              : `/portafolio/${slug}/market?tab=${t.key}`
          return (
            <Link
              key={t.key}
              href={href}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                isActive
                  ? 'border-foreground/40 bg-surface-secondary text-foreground'
                  : 'border-border text-muted hover:text-foreground hover:bg-surface-secondary'
              }`}
            >
              <span>{t.label}</span>
              <span className="ml-2 text-[10px] opacity-60">· {t.hint}</span>
            </Link>
          )
        })}
      </nav>

      {active === 'pulse' && <PulseTab />}
      {active === 'mechanics' && <MechanicsTab />}
      {active === 'rotation' && <RotationTab />}
      {active === 'macro' && <MacroTab />}
    </div>
  )
}
