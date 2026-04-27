export const PORTFOLIO_ROLES = [
  { label: 'Owner', value: 'owner' },
  { label: 'Admin', value: 'admin' },
  { label: 'Trader', value: 'trader' },
  { label: 'Viewer', value: 'viewer' },
] as const

export type PortfolioRole = 'owner' | 'admin' | 'trader' | 'viewer'

export function canDeleteMembership(
  roleBeingDeleted: string,
  totalOwnersInPortfolio: number,
): boolean {
  if (roleBeingDeleted === 'owner' && totalOwnersInPortfolio <= 1) {
    return false
  }
  return true
}

export function isAdminRole(role: string): boolean {
  return role === 'owner' || role === 'admin'
}
