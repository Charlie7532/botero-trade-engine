import { redirect } from 'next/navigation'

import { getServerUser } from '@/providers/Auth/server'
import { getOrCreateDefaultPortfolio } from '@/collections/Portfolios/interface/service'

export default async function PortafolioIndexPage() {
  const { user } = await getServerUser()

  const portfolio = await getOrCreateDefaultPortfolio(user.id, user.email)
  redirect(`/portafolio/${portfolio.slug}`)
}
