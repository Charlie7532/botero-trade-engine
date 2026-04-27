import type { CollectionConfig } from 'payload'

import { isPortfolioMember, isPortfolioAdmin } from '@/access'
import { brokerAccountsFields } from './fields'
import { brokerAccountsLifecycle } from './lifecycle'

export const BrokerAccounts: CollectionConfig = {
  slug: 'broker-accounts',
  access: {
    create: isPortfolioAdmin(),
    read: isPortfolioMember(),
    update: isPortfolioAdmin(),
    delete: isPortfolioAdmin(),
  },
  admin: {
    group: 'Trading',
    defaultColumns: ['name', 'portfolio', 'brokerType', 'environment', 'isActive'],
    useAsTitle: 'name',
  },
  hooks: brokerAccountsLifecycle,
  fields: brokerAccountsFields,
  timestamps: true,
}
