import { authenticated } from '@/access'
import { isPortfolioMember } from '@/access/isPortfolioMember'

export const portfoliosAccess = {
  create: authenticated,
  read: isPortfolioMember({ portfolioField: 'id' }),
  update: isPortfolioMember({ portfolioField: 'id', requiredRoles: ['owner', 'admin'] }),
  delete: isPortfolioMember({ portfolioField: 'id', requiredRoles: ['owner'] }),
}
