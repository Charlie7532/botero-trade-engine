import type { Payload } from 'payload'

import type { PortfolioCreator } from '../domain/ports/PortfolioCreator'
import type { UserPortfolioSummary } from '../domain/ports/UserPortfolioReader'

export function createPayloadPortfolioCreator(payload: Payload): PortfolioCreator {
  return {
    async create({ name, ownerId }): Promise<UserPortfolioSummary> {
      const doc = await payload.create({
        collection: 'portfolios',
        data: {
          name,
          owner: ownerId,
        },
        overrideAccess: true,
      })

      return {
        id: doc.id,
        slug: doc.slug as string,
        name: doc.name,
        status: String(doc.status),
        role: 'owner',
      }
    },
  }
}
