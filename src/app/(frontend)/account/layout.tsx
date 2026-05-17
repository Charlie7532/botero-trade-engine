import Link from 'next/link'
import type { ReactNode } from 'react'
import { Home } from 'lucide-react'

import { userSession } from '@/providers/Auth/server'

export default async function AccountLayout({ children }: { children: ReactNode }) {
  const { user } = await userSession()
  if (!user) return null

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-5xl px-8 py-10">
        <div className="flex justify-start mb-8">
          <nav className="flex items-center gap-1.5 text-xs text-muted" aria-label="Breadcrumb">
            <Link className="hover:text-foreground transition-colors" href="/portafolio">
              <Home className="size-3.5" aria-label="Home" />
            </Link>
            <span>/</span>
            <span className="text-foreground">Account</span>
          </nav>
        </div>

        {children}
      </div>
    </div>
  )
}
