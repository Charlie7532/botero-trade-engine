import type { Access } from 'payload'

import { isPortfolioMember } from './isPortfolioMember'

type PortfolioAdminOptions = {
  portfolioField?: string
}

export const isPortfolioAdmin = ({
  portfolioField = 'portfolio',
}: PortfolioAdminOptions = {}): Access => {
  return isPortfolioMember({
    portfolioField,
    requiredRoles: ['owner', 'admin'],
  })
}
