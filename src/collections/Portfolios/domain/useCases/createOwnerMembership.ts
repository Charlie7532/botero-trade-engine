export interface CreateOwnerMembershipInput {
  portfolioId: string
  userId: string
}

export interface OwnerMembershipData {
  portfolio: string
  user: string
  portfolioRole: 'owner'
  invitedBy: string
  joinedAt: string
}

export function buildOwnerMembership(input: CreateOwnerMembershipInput): OwnerMembershipData {
  return {
    portfolio: input.portfolioId,
    user: input.userId,
    portfolioRole: 'owner',
    invitedBy: input.userId,
    joinedAt: new Date().toISOString(),
  }
}
