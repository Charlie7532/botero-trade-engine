import type { Field } from 'payload'

import {
  BROKER_TYPES,
  ENVIRONMENTS,
  ALPACA_BASE_URLS,
  IB_DEFAULT_HOST,
  IB_DEFAULT_PORT_PAPER,
} from './domain/rules/portfolioRules'

export const brokerAccountsFields: Field[] = [
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    required: true,
    index: true,
  },
  {
    name: 'name',
    type: 'text',
    required: true,
  },
  {
    name: 'brokerType',
    type: 'select',
    required: true,
    options: [...BROKER_TYPES],
  },
  {
    name: 'environment',
    type: 'select',
    required: true,
    defaultValue: 'paper',
    options: [...ENVIRONMENTS],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: true,
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'alpacaBaseUrl',
    type: 'text',
    defaultValue: ALPACA_BASE_URLS.paper,
    admin: {
      condition: (data) => data?.brokerType === 'alpaca',
    },
  },
  {
    name: 'ibHost',
    type: 'text',
    defaultValue: IB_DEFAULT_HOST,
    admin: {
      condition: (data) => data?.brokerType === 'interactive_brokers',
    },
  },
  {
    name: 'ibPort',
    type: 'number',
    defaultValue: IB_DEFAULT_PORT_PAPER,
    admin: {
      condition: (data) => data?.brokerType === 'interactive_brokers',
    },
  },
  {
    name: 'ibAccountId',
    type: 'text',
    admin: {
      condition: (data) => data?.brokerType === 'interactive_brokers',
    },
  },
  {
    name: 'ibClientId',
    type: 'number',
    defaultValue: 1,
    admin: {
      condition: (data) => data?.brokerType === 'interactive_brokers',
    },
  },
]
