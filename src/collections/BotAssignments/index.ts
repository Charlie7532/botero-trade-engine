import type { CollectionConfig } from 'payload'

import { botAssignmentsAccess } from './access'
import { botAssignmentsFields } from './fields'
import { botAssignmentsLifecycle } from './lifecycle'

export const BotAssignments: CollectionConfig = {
  slug: 'bot-assignments',
  access: botAssignmentsAccess,
  admin: {
    hidden: true,
    defaultColumns: ['bot', 'portfolio', 'isActive'],
    useAsTitle: 'bot',
  },
  hooks: botAssignmentsLifecycle,
  fields: botAssignmentsFields,
  timestamps: true,
}
