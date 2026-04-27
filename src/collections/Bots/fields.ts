import type { Field } from 'payload'

import { BOT_STATUSES, STRATEGY_TYPES } from './domain/rules/botRules'

export const botsFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
  },
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    required: true,
    index: true,
  },
  {
    name: 'strategyType',
    type: 'select',
    required: true,
    options: [...STRATEGY_TYPES],
  },
  {
    name: 'status',
    type: 'select',
    required: true,
    defaultValue: 'stopped',
    options: [...BOT_STATUSES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'description',
    type: 'textarea',
  },
  {
    name: 'config',
    type: 'json',
    admin: {
      description: 'Strategy-specific configuration (parameters, thresholds, filters).',
    },
  },
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Broker Account Assignments',
        fields: [
          {
            name: 'assignments',
            type: 'join',
            collection: 'bot-assignments',
            on: 'bot',
          },
        ],
      },
    ],
  },
]
