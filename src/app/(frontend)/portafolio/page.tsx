import { redirect } from 'next/navigation'

import { userSession } from '@/providers/Auth/server'
import { getOrCreateDefaultPortfolio } from '@/collections/Portfolios/interface/service'

export default async function PortafolioIndexPage() {
  const { user } = await userSession()

  if (!user) return null;
  
  const portfolio = await getOrCreateDefaultPortfolio(user.id, user.email)
  redirect(`/portafolio/${portfolio.slug}`)
}
