import type { CollectionConfig } from 'payload'

import { portfoliosAccess } from './access'
import { portfoliosFields } from './fields'
import { portfoliosLifecycle } from './lifecycle'

export const Portfolios: CollectionConfig = {
  slug: 'portfolios',
  access: portfoliosAccess,
  admin: {
    group: 'Users & Portfolios',
    defaultColumns: ['name', 'slug', 'status', 'owner'],
    useAsTitle: 'name',
  },
  hooks: portfoliosLifecycle,
  fields: portfoliosFields,
  timestamps: true,
}
