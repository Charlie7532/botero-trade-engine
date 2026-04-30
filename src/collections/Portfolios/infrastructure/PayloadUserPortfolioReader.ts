import type { Payload } from 'payload'

import type { UserPortfolioReader, UserPortfolioSummary } from '../domain/ports/UserPortfolioReader'

function relationId(value: unknown): number | string | null {
  if (typeof value === 'object' && value !== null && 'id' in (value as Record<string, unknown>)) {
    return (value as { id: number | string }).id
  }

  if (typeof value === 'number' || typeof value === 'string') return value

  return null
}

export function createPayloadUserPortfolioReader(payload: Payload): UserPortfolioReader {
  return {
    async listByUserId(userId: number | string): Promise<UserPortfolioSummary[]> {
      const memberships = await payload.find({
        collection: 'portfolio-memberships',
        where: {
          user: { equals: userId },
        },
        depth: 0,
        limit: 100,
        overrideAccess: true,
      })

      if (!memberships.docs.length) return []

      const roleByPortfolio = new Map<number | string, string>()

      const portfolioIds = memberships.docs
        .map((membership) => {
          const portfolioId = relationId(membership.portfolio)
          if (!portfolioId) return null

          roleByPortfolio.set(portfolioId, String(membership.portfolioRole || 'viewer'))
          return portfolioId
        })
        .filter((id): id is number | string => id !== null)

      if (!portfolioIds.length) return []

      const portfolios = await payload.find({
        collection: 'portfolios',
        where: {
          id: {
            in: portfolioIds,
          },
        },
        depth: 0,
        limit: portfolioIds.length,
        overrideAccess: true,
      })

      return portfolios.docs
        .map((portfolio) => {
          const slug =
            typeof portfolio.slug === 'string' && portfolio.slug.length > 0
              ? portfolio.slug
              : String(portfolio.id)

          return {
            id: portfolio.id,
            slug,
            name: String(portfolio.name || 'Untitled Portfolio'),
            status: String((portfolio as unknown as Record<string, unknown>).status || 'active'),
            role: roleByPortfolio.get(portfolio.id) || 'viewer',
          }
        })
        .sort((a, b) => a.name.localeCompare(b.name))
    },
  }
}
