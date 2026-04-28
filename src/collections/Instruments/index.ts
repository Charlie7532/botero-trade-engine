import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { instrumentsFields } from './fields'

export const Instruments: CollectionConfig = {
  slug: 'instruments',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Trading Engine',
    defaultColumns: ['ticker', 'name', 'instrumentType', 'gicsSector', 'universe', 'isActive'],
    useAsTitle: 'ticker',
  },
  fields: instrumentsFields,
  timestamps: true,
}
