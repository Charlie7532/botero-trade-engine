import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { regimePhasesFields } from './fields'

export const RegimePhases: CollectionConfig = {
  slug: 'regime-phases',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Trading Engine',
    defaultColumns: ['instrument', 'level', 'phase', 'detectedAt', 'closedAt'],
    useAsTitle: 'phase',
  },
  fields: regimePhasesFields,
  timestamps: true,
}
