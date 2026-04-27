import type { Field } from 'payload'

import { PORTFOLIO_ROLES } from './domain/rules/membershipRules'

export const portfolioMembershipsFields: Field[] = [
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    required: true,
    index: true,
  },
  {
    name: 'user',
    type: 'relationship',
    relationTo: 'users',
    required: true,
    index: true,
  },
  {
    name: 'portfolioRole',
    type: 'select',
    required: true,
    defaultValue: 'viewer',
    options: [...PORTFOLIO_ROLES],
  },
  {
    name: 'invitedBy',
    type: 'relationship',
    relationTo: 'users',
    admin: {
      readOnly: true,
      position: 'sidebar',
    },
  },
  {
    name: 'joinedAt',
    type: 'date',
    admin: {
      readOnly: true,
      position: 'sidebar',
    },
  },
]
