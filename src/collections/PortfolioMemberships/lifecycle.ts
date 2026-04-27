import { handleBeforeChangeHook } from '@/shared/handlers'
import { canDeleteMembership } from './domain/rules/membershipRules'
import type { CollectionBeforeDeleteHook } from 'payload'

const setInvitedByAndJoinedAt = handleBeforeChangeHook({
  name: 'PortfolioMemberships',
  operation: 'create',
  handler: async ({ data, req }) => {
    if (req.user && !data.invitedBy) {
      data.invitedBy = req.user.id
    }

    if (!data.joinedAt) {
      data.joinedAt = new Date().toISOString()
    }

    return data
  },
})

const preventOrphanPortfolio: CollectionBeforeDeleteHook = async ({ id, req }) => {
  const membership = await req.payload.findByID({
    collection: 'portfolio-memberships' as any,
    id,
    overrideAccess: true,
    depth: 0,
  })

  if (!membership) return

  const role = (membership as any).portfolioRole
  if (role !== 'owner') return

  const portfolioId = typeof (membership as any).portfolio === 'object' && (membership as any).portfolio !== null
    ? (membership as any).portfolio.id
    : (membership as any).portfolio

  const { totalDocs } = await req.payload.count({
    collection: 'portfolio-memberships' as any,
    where: {
      portfolio: { equals: portfolioId },
      portfolioRole: { equals: 'owner' },
    },
    overrideAccess: true,
  })

  if (!canDeleteMembership('owner', totalDocs)) {
    throw new Error('Cannot delete the last owner of a portfolio. Transfer ownership first.')
  }
}

export const portfolioMembershipsLifecycle = {
  beforeChange: [setInvitedByAndJoinedAt],
  beforeDelete: [preventOrphanPortfolio],
}
