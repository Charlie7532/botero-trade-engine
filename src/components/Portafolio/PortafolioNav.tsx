'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Dropdown, Button, Label } from '@heroui/react'
import {
  LayoutDashboard,
  LineChart,
  Bot,
  Plug,
  Plus,
  Check,
  ChevronsUpDown,
  Briefcase,
} from 'lucide-react'

import type { UserPortfolioSummary } from '@/collections/Portfolios/interface/service'
import NewPortafolioDialog from './NewPortafolioDialog'

type NavItem = {
  label: string
  href: (slug: string) => string
  icon: React.ComponentType<{ size?: number; className?: string }>
  match: (pathname: string, slug: string) => boolean
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Overview',
    href: (slug) => `/portafolio/${slug}`,
    icon: LayoutDashboard,
    match: (p, slug) => p === `/portafolio/${slug}`,
  },
  {
    label: 'Market Analysis',
    href: (slug) => `/portafolio/${slug}/market`,
    icon: LineChart,
    match: (p, slug) => p.startsWith(`/portafolio/${slug}/market`),
  },
  {
    label: 'Agents & Strategies',
    href: (slug) => `/portafolio/${slug}/agents`,
    icon: Bot,
    match: (p, slug) => p.startsWith(`/portafolio/${slug}/agents`),
  },
  {
    label: 'Broker Accounts',
    href: (slug) => `/portafolio/${slug}/brokers`,
    icon: Plug,
    match: (p, slug) => p.startsWith(`/portafolio/${slug}/brokers`),
  },
]

type Props = {
  portfolios: UserPortfolioSummary[]
}

const PortafolioNav: React.FC<Props> = ({ portfolios }) => {
  const pathname = usePathname() ?? '/portafolio'
  const [isNewOpen, setIsNewOpen] = useState(false)

  // Detect active portfolio from URL: /portafolio/{slug}/...
  const slugMatch = pathname.match(/^\/portafolio\/([^/]+)/)
  const activeSlug = slugMatch?.[1]
  const active = portfolios.find((p) => p.slug === activeSlug) ?? portfolios[0]

  const handleSelect = (key: React.Key) => {
    if (key === '__new__') {
      setIsNewOpen(true)
      return
    }
    window.location.href = `/portafolio/${String(key)}`
  }

  return (
    <>
      {/* Portfolio switcher */}
      <div className="px-3 pt-4 pb-2">
        <Dropdown>
          <Button
            variant="ghost"
            className="!w-full !justify-start gap-2 px-2 py-2 h-auto rounded-lg border border-border hover:bg-surface-secondary"
          >
            <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-surface-secondary text-foreground">
              <Briefcase size={14} />
            </span>
            <span className="flex min-w-0 flex-1 flex-col items-start text-left">
              <span className="text-[10px] font-semibold tracking-widest uppercase text-muted leading-tight">
                Portfolio
              </span>
              <span className="truncate text-sm font-medium text-foreground leading-tight">
                {active?.name ?? 'No portfolio'}
              </span>
            </span>
            <ChevronsUpDown size={14} className="ml-auto shrink-0 text-muted" />
          </Button>
          <Dropdown.Popover placement="bottom start">
            <Dropdown.Menu aria-label="Switch portfolio" onAction={handleSelect}>
              {portfolios.map((p) => (
                <Dropdown.Item key={p.id} id={p.slug} textValue={p.name}>
                  <Briefcase size={16} />
                  <Label>{p.name}</Label>
                  {active?.slug === p.slug ? <Check size={14} className="ml-auto text-muted" /> : null}
                </Dropdown.Item>
              ))}
              <Dropdown.Item id="__new__" textValue="New portfolio">
                <Plus size={16} />
                <Label>New portfolio</Label>
              </Dropdown.Item>
            </Dropdown.Menu>
          </Dropdown.Popover>
        </Dropdown>
      </div>

      {/* Page navigation — slug-aware */}
      <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
        {active ? (
          NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const href = item.href(active.slug)
            const isActive = item.match(pathname, active.slug)
            return (
              <Link
                key={item.label}
                href={href}
                className={[
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-surface-secondary text-foreground font-medium'
                    : 'text-foreground hover:bg-surface-secondary',
                ].join(' ')}
              >
                <Icon size={16} className="shrink-0 text-muted" />
                <span className="truncate">{item.label}</span>
              </Link>
            )
          })
        ) : (
          <button
            type="button"
            onClick={() => setIsNewOpen(true)}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-foreground hover:bg-surface-secondary transition-colors"
          >
            <Plus size={16} />
            <span>Create your first portfolio</span>
          </button>
        )}
      </nav>

      <NewPortafolioDialog isOpen={isNewOpen} onOpenChange={setIsNewOpen} />
    </>
  )
}

export default PortafolioNav
