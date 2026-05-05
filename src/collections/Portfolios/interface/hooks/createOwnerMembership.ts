import { handleAfterChangeHook } from '@/shared/handlers'
import { buildOwnerMembership } from '../../domain/rules/accountRules'

export const createOwnerMembershipHook = handleAfterChangeHook({
  name: 'Portfolios',
  operation: 'create',
  handler: async ({ doc, req }) => {
    const userId = doc.owner
    if (!userId) return doc

    const ownerId =
      typeof userId === 'object' && userId !== null
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
