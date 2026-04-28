import type { Field } from 'payload'

import {
  BROKER_TYPES,
  ENVIRONMENTS,
} from './domain/rules/portfolioRules'

const isBroker = (target: 'alpaca' | 'interactive_brokers') => {
  return (data: Record<string, unknown>) => {
    const brokerType = (data as Record<string, any>)?.brokerType
    return brokerType === target
  }
}

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
    label: 'Broker',
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
    type: 'tabs',
    tabs: [
      {
        label: 'Credentials',
        fields: [
          {
            name: 'apiKeyPlaintext',
            type: 'text',
            required: false,
            admin: {
              description: 'Required for Alpaca. Enter your API Key here.',
              condition: isBroker('alpaca'),
            },
            hooks: {
              afterRead: [
                () => undefined,
              ],
            },
          },
          {
            name: 'apiKeyMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('alpaca'),
              description: 'Your API key (last 4 digits only for security).',
            },
            access: {
              update: () => false,
            },
          },
          {
            name: 'secretKeyPlaintext',
            type: 'text',
            required: false,
            admin: {
              description: 'Required for Alpaca. Enter your Secret Key here.',
              condition: isBroker('alpaca'),
            },
            hooks: {
              afterRead: [
                () => undefined,
              ],
            },
          },
          {
            name: 'secretKeyMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('alpaca'),
              description: 'Your secret key (last 4 digits only for security).',
            },
            access: {
              update: () => false,
            },
          },
          {
            name: 'ibAccountId',
            type: 'text',
            required: false,
            admin: {
              description: 'Required for Interactive Brokers. Your IB Account ID.',
              condition: isBroker('interactive_brokers'),
            },
          },
        ],
      },
      {
        label: 'Advanced Settings',
        fields: [
          {
            name: 'alpacaBaseUrl',
            type: 'text',
            admin: {
              condition: isBroker('alpaca'),
              description: 'Alpaca API base URL (defaults to paper trading URL).',
            },
          },
          {
            name: 'ibHost',
            type: 'text',
            admin: {
              condition: isBroker('interactive_brokers'),
              description: 'Interactive Brokers host (e.g., 127.0.0.1).',
            },
          },
          {
            name: 'ibPort',
            type: 'number',
            admin: {
              condition: isBroker('interactive_brokers'),
              description: 'Interactive Brokers port.',
            },
          },
          {
            name: 'ibClientId',
            type: 'number',
            admin: {
              condition: isBroker('interactive_brokers'),
              description: 'Interactive Brokers client ID.',
            },
          },
        ],
      },
      {
        label: 'Bot Deployments',
        fields: [
          {
            name: 'botsInfo',
            type: 'text',
            admin: {
              readOnly: true,
              description: 'View all bots assigned to this broker account in Portfolio > Bot Assignments. Manage bot-to-account mappings at the portfolio level for a complete deployment strategy.',
            },
            access: {
              create: () => false,
              update: () => false,
            },
          },
        ],
      },
    ],
  },
  // Encrypted credential storage (hidden)
  {
    name: 'apiKeyEncrypted',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'apiKeyIv',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'apiKeyAuthTag',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'secretKeyEncrypted',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'secretKeyIv',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'secretKeyAuthTag',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
]
