import { randomBytes } from 'node:crypto'

const SLUG_PATTERN = /^[a-z0-9]{12}$/

export function generatePortfolioSlug(): string {
  return randomBytes(6).toString('hex') // 6 bytes = 12 hex chars
}

export function isValidPortfolioSlug(slug: string): boolean {
  return SLUG_PATTERN.test(slug)
}

export function isPortfolioOwner(userId: string, ownerId: string): boolean {
  return userId === ownerId
}

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function isValidSlug(value: unknown): boolean {
  if (typeof value !== 'string' || !value) return false
  return isValidPortfolioSlug(value) || UUID_V4_PATTERN.test(value)
}

export function buildDefaultPortfolioName(email: string): string {
  return `${email}'s portfolio`
}

export const PORTFOLIO_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Suspended', value: 'suspended' },
  { label: 'Archived', value: 'archived' },
] as const

// ── Owner Membership Builder ─────────────────────────────────────────────────
// Pure data constructor — no side effects, no I/O.

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
