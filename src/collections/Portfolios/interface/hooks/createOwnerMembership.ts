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
      // Failing silently here leaves the portfolio doc in the DB with no owner
      // membership, which makes the portfolio unreachable from the UI (the
      // sidebar lists portfolios via memberships and the dashboard 404s).
      // Best-effort rollback so the user sees a clean error and can retry.
      console.error('[Portfolios] Failed to create owner membership:', error)
      try {
        await req.payload.delete({
          collection: 'portfolios',
          id: doc.id,
          overrideAccess: true,
        })
      } catch (cleanupError) {
        console.error(
          '[Portfolios] Failed to roll back portfolio after membership error:',
          cleanupError,
        )
      }
      throw error instanceof Error
        ? error
        : new Error('Failed to create owner membership for portfolio.')
    }

    return doc
  },
})
