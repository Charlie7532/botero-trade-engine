import { redirect } from 'next/navigation'

import { getUser } from '@/providers/Auth/server'
import {
	getOrCreateDefaultPortfolio,
	getUserPortfolios,
} from '@/collections/Portfolios/interface/service'

export default async function FrontendHomePage() {
	const user = await getUser()

	if (!user) {
		redirect('/login?redirect=%2Fportafolio')
	}

	const portfolios = await getUserPortfolios(user.id)
	const portfolio = portfolios[0] ?? (await getOrCreateDefaultPortfolio(user.id, user.email))

	redirect(`/portafolio/${portfolio.slug}`)
}
