import type { Field } from 'payload'

export const botAssignmentsFields: Field[] = [
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    required: true,
    index: true,
    admin: {
      description: 'Portfolio this bot assignment belongs to.',
    },
  },
  {
    name: 'bot',
    type: 'relationship',
    relationTo: 'bots',
    required: true,
    index: true,
    admin: {
      description: 'The bot strategy to deploy.',
    },
    filterOptions: ({ siblingData }) => {
      const portfolio = (siblingData as Record<string, any>)?.portfolio
      if (!portfolio) return true
      return { portfolio: { equals: portfolio } }
    },
  },
  {
    name: 'brokerAccount',
    type: 'relationship',
    relationTo: 'broker-accounts',
    required: true,
    index: true,
    admin: {
      description: 'The broker account where this bot will execute.',
    },
    filterOptions: ({ siblingData }) => {
      const portfolio = (siblingData as Record<string, any>)?.portfolio
      if (!portfolio) return true
      return { portfolio: { equals: portfolio } }
    },
  },
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: false,
    admin: {
      position: 'sidebar',
      description: 'Enable this bot on the selected broker account.',
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
