import { handleBeforeChangeHook, handleAfterChangeHook } from '@/shared/handlers'
import { generateSlug } from './domain/rules/accountRules'
import { buildOwnerMembership } from './domain/useCases/createOwnerMembership'

const autoGenerateSlugAndOwner = handleBeforeChangeHook({
  name: 'Portfolios',
  operation: 'create',
  handler: async ({ data, req }) => {
    if (data.name && !data.slug) {
      data.slug = generateSlug(data.name)
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
      ? String((userId as unknown as { id: number | string }).id)
      : String(userId)

    const membershipData = buildOwnerMembership({
      portfolioId: String(doc.id),
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
