import type { Access } from 'payload'

const botAssignmentAccess = (requiredRoles: string[] = []): Access => {
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
      const portfolio = (m as any).portfolio
      return typeof portfolio === 'object' && portfolio !== null
        ? (portfolio as unknown as { id: number | string }).id
        : portfolio
    })

    return {
      portfolio: {
        in: portfolioIds,
      },
    }
  }
}

const adminAccess = botAssignmentAccess(['owner', 'admin'])
const memberAccess = botAssignmentAccess()

export const botAssignmentsAccess = {
  create: adminAccess,
  read: memberAccess,
  update: adminAccess,
  delete: adminAccess,
}
