import type { Field } from 'payload'

export const botAssignmentsFields: Field[] = [
  {
    name: 'bot',
    type: 'relationship',
    relationTo: 'bots',
    required: true,
    index: true,
  },
  {
    name: 'brokerAccount',
    type: 'relationship',
    relationTo: 'broker-accounts',
    required: true,
    index: true,
  },
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: false,
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'riskLimits',
    type: 'group',
    fields: [
      {
        name: 'maxPositionSize',
        type: 'number',
        admin: {
          description: 'Max % of portfolio value per position.',
        },
      },
      {
        name: 'maxDailyLoss',
        type: 'number',
        admin: {
          description: 'Max daily loss % before bot auto-pauses.',
        },
      },
      {
        name: 'maxOpenPositions',
        type: 'number',
        admin: {
          description: 'Max concurrent open positions.',
        },
      },
    ],
  },
]
