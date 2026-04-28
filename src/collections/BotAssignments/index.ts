import type { CollectionConfig } from 'payload'

import { botAssignmentsAccess } from './access'
import { botAssignmentsFields } from './fields'
import { botAssignmentsLifecycle } from './lifecycle'

export const BotAssignments: CollectionConfig = {
  slug: 'bot-assignments',
  access: botAssignmentsAccess,
  admin: {
     group: 'Accounts',
     defaultColumns: ['portfolio', 'bot', 'brokerAccount', 'isActive'],
    useAsTitle: 'bot',
  },
  hooks: botAssignmentsLifecycle,
  fields: botAssignmentsFields,
  timestamps: true,
}
