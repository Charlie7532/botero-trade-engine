import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import type { ReactNode } from 'react'
import { Home } from 'lucide-react'

import { getServerUser } from '@/providers/Auth/server'
import { getUserPortfolios } from '@/collections/Portfolios/interface/service'

type LayoutProps = {
  children: ReactNode
  params: Promise<{ slug: string }>
}

const NAV_ITEMS = [
  { label: 'Portfolio', href: (slug: string) => `/portafolio/${slug}/settings` },
  { label: 'Profile', href: (slug: string) => `/portafolio/${slug}/settings/profile` },
  { label: 'Members', href: (slug: string) => `/portafolio/${slug}/settings/members` },
]

export default async function SettingsLayout({ children, params }: LayoutProps) {
  const { slug } = await params

  const { user } = await getServerUser()

  if (!user) {
    redirect('/login?redirect=%2Fportafolio')
  }

  const portfolios = await getUserPortfolios(user.id)
  const portfolio = portfolios.find((p) => p.slug === slug)

  if (!portfolio) notFound()

  return (
    <div className="flex min-h-screen">
      {/* Sidebar — full height, flush to left edge */}
      <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-border bg-surface">
        <div className="px-5 py-8 border-b border-border">
          <Link
            className="inline-flex items-center justify-center size-7 rounded-lg text-muted hover:text-foreground hover:bg-surface-secondary transition-colors"
            href={`/portafolio/${slug}`}
            aria-label="Back to portfolio"
          >
            <svg className="size-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path d="M15.75 19.5L8.25 12l7.5-7.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
          <p className="mt-3 text-sm font-semibold text-foreground">Settings</p>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.label}
              className="flex items-center rounded-lg px-3 py-2 text-sm text-foreground hover:bg-surface-secondary transition-colors"
              href={item.href(slug)}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      {/* Content area */}
      <div className="flex-1 min-w-0">
        <div className="mx-auto max-w-5xl px-8 py-10">
          {/* Breadcrumb — top left of content area */}
          <div className="flex justify-start mb-8">
            <nav className="flex items-center gap-1.5 text-xs text-muted" aria-label="Breadcrumb">
              <Link className="hover:text-foreground transition-colors" href="/portafolio">
                <Home className="size-3.5" aria-label="Home" />
              </Link>
              <span>/</span>
              <Link className="hover:text-foreground transition-colors" href={`/portafolio/${slug}`}>
                {portfolio.name}
              </Link>
              <span>/</span>
              <span className="text-foreground">Settings</span>
            </nav>
          </div>

          {children}
        </div>
      </div>
    </div>
  )
}
