import type { CollectionConfig } from 'payload'

import { isPortfolioMember, isPortfolioAdmin } from '@/access'
import { botsFields } from './fields'
import { botsLifecycle } from './lifecycle'

export const Bots: CollectionConfig = {
  slug: 'bots',
  access: {
    create: isPortfolioAdmin(),
    read: isPortfolioMember(),
    update: isPortfolioAdmin(),
    delete: isPortfolioAdmin(),
  },
  admin: {
    group: 'Trading',
    defaultColumns: ['name', 'portfolio', 'strategyType', 'status'],
    useAsTitle: 'name',
  },
  hooks: botsLifecycle,
  fields: botsFields,
  timestamps: true,
}
