import { handleBeforeChangeHook, handleAfterChangeHook } from '@/shared/handlers'
import { generatePortfolioSlug, isValidPortfolioSlug } from './domain/rules/accountRules'
import { buildOwnerMembership } from './domain/useCases/createOwnerMembership'

const autoGenerateSlugAndOwner = handleBeforeChangeHook({
  name: 'Portfolios',
  operation: ['create', 'update'],
  handler: async ({ data, req }) => {
    if (!data.slug) {
      data.slug = generatePortfolioSlug()
    } else if (!isValidPortfolioSlug(String(data.slug))) {
      throw new Error('Portfolio slug must be a valid UUID v4.')
    }

    if (req.user && !data.owner) {
      data.owner = req.user.id
    }

    return data
  },
})

const createOwnerMembership = handleAfterChangeHook({
  name: 'Portfolios',
  operation: 'create',
  handler: async ({ doc, req }) => {
    const userId = doc.owner
    if (!userId) return doc

    const ownerId = typeof userId === 'object' && userId !== null
      ? (userId as unknown as { id: number | string }).id
      : userId

    const membershipData = buildOwnerMembership({
      portfolioId: doc.id as number | string,
      userId: ownerId,
    })

    try {
      await req.payload.create({
        collection: 'portfolio-memberships' as any,
        data: membershipData as any,
        overrideAccess: true,
      })
    } catch (error) {
      console.error('[Portfolios] Failed to create owner membership:', error)
    }

    return doc
  },
})

export const portfoliosLifecycle = {
  beforeChange: [autoGenerateSlugAndOwner],
  afterChange: [createOwnerMembership],
}
