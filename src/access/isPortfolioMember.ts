import type { Access } from 'payload'

type PortfolioMemberOptions = {
  portfolioField?: string
  requiredRoles?: string[]
}

export const isPortfolioMember = ({
  portfolioField = 'portfolio',
  requiredRoles = [],
}: PortfolioMemberOptions = {}): Access => {
  return async ({ req }) => {
    const { user, payload } = req

    if (!user) return false

    if ((user as { role?: string }).role === 'superadmin') return true

    const memberships = await payload.find({
      collection: 'portfolio-memberships',
      where: {
        user: { equals: user.id },
        ...(requiredRoles.length > 0
          ? { portfolioRole: { in: requiredRoles } }
          : {}),
      },
      limit: 100,
      depth: 0,
      overrideAccess: true,
    })

    if (memberships.totalDocs === 0) return false

    const portfolioIds = memberships.docs.map((m) => {
      const portfolio = m.portfolio
      return typeof portfolio === 'object' && portfolio !== null
        ? (portfolio as unknown as { id: number | string }).id
        : portfolio
    })

    return {
      [portfolioField]: {
        in: portfolioIds,
      },
    }
  }
}
