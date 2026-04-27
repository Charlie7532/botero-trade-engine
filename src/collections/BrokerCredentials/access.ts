import type { Access } from 'payload'

const credentialBrokerAccountAccess = (requiredRoles: string[] = []): Access => {
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

    const brokerAccounts = await payload.find({
      collection: 'broker-accounts',
      where: {
        portfolio: { in: portfolioIds },
      },
      limit: 500,
      depth: 0,
      overrideAccess: true,
    })

    if (brokerAccounts.totalDocs === 0) return false

    const brokerAccountIds = brokerAccounts.docs.map((ba) => ba.id)

    return {
      brokerAccount: {
        in: brokerAccountIds,
      },
    }
  }
}

const adminAccess = credentialBrokerAccountAccess(['owner', 'admin'])

export const brokerCredentialsAccess = {
  create: adminAccess,
  read: adminAccess,
  update: adminAccess,
  delete: adminAccess,
}
