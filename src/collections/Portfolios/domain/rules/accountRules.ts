import { randomUUID } from 'node:crypto'

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function generatePortfolioSlug(): string {
  return randomUUID()
}

export function isValidPortfolioSlug(slug: string): boolean {
  return UUID_V4_PATTERN.test(slug)
}

export function isPortfolioOwner(userId: string, ownerId: string): boolean {
  return userId === ownerId
}

export const PORTFOLIO_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Suspended', value: 'suspended' },
  { label: 'Archived', value: 'archived' },
] as const
