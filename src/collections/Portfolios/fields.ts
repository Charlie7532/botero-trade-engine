import type { Field } from 'payload'

import { isAdminFieldLevel } from '@/access'
import { isValidPortfolioSlug, PORTFOLIO_STATUSES } from './domain/rules/accountRules'

export const portfoliosFields: Field[] = [
  {
    name: 'name',
    type: 'text',
    required: true,
  },
  {
    name: 'slug',
    type: 'text',
    unique: true,
    index: true,
    validate: (value: unknown) => {
      if (typeof value !== 'string' || !value) return 'Slug is required.'
      return isValidPortfolioSlug(value) || 'Slug must be a valid UUID v4.'
    },
    admin: {
      readOnly: true,
    },
  },
  {
    name: 'portfolio_status',
    label: 'Portfolio Status',
    type: 'select',
    required: true,
    defaultValue: 'active',
    options: [...PORTFOLIO_STATUSES],
    access: {
      update: isAdminFieldLevel,
    },
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'owner',
    type: 'relationship',
    relationTo: 'users',
    required: true,
    index: true,
    admin: {
      position: 'sidebar',
    },
  },
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Broker Accounts',
        fields: [
          {
            name: 'brokerAccounts',
            type: 'join',
            collection: 'broker-accounts',
            on: 'portfolio',
          },
        ],
      },
      {
        label: 'Bots',
        fields: [
          {
            name: 'bots',
            type: 'join',
            collection: 'bots',
            on: 'portfolio',
          },
        ],
      },
      {
        label: 'Members',
        fields: [
          {
            name: 'members',
            type: 'join',
            collection: 'portfolio-memberships',
            on: 'portfolio',
          },
        ],
      },
    ],
  },
]
