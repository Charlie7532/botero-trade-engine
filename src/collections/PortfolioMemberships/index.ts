import type { CollectionConfig } from 'payload'

import { isPortfolioMember, isPortfolioAdmin } from '@/access'
import { portfolioMembershipsFields } from './fields'
import { portfolioMembershipsLifecycle } from './lifecycle'

export const PortfolioMemberships: CollectionConfig = {
  slug: 'portfolio-memberships',
  access: {
    create: isPortfolioAdmin(),
    read: isPortfolioMember(),
    update: isPortfolioAdmin(),
    delete: isPortfolioAdmin(),
  },
  admin: {
    hidden: true,
    defaultColumns: ['portfolio', 'user', 'portfolioRole', 'joinedAt'],
    useAsTitle: 'portfolioRole',
  },
  hooks: portfolioMembershipsLifecycle,
  fields: portfolioMembershipsFields,
  timestamps: true,
}
