type RelationId = number | string

export interface CreateOwnerMembershipInput {
  portfolioId: RelationId
  userId: RelationId
}

export interface OwnerMembershipData {
  portfolio: RelationId
  user: RelationId
  portfolioRole: 'owner'
  invitedBy: RelationId
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
