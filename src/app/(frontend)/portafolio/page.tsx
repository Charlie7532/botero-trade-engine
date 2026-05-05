import { redirect } from 'next/navigation'

import { getMeUser } from '@/utilities/getMeUser'
import { getOrCreateDefaultPortfolio } from '@/collections/Portfolios/interface/service'

export default async function PortafolioIndexPage() {
  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const portfolio = await getOrCreateDefaultPortfolio(user.id, user.email)
  redirect(`/portafolio/${portfolio.slug}`)
}
