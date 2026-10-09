import type { Field } from 'payload'

import {
  BROKER_TYPES,
  DEPARTMENTS,
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
    name: 'department',
    label: 'Department',
    type: 'select',
    required: true,
    defaultValue: 'quality',
    options: [...DEPARTMENTS],
    admin: {
      position: 'sidebar',
      description: 'Which strategy department this broker account serves.',
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
              description: 'Required for Interactive Brokers. Your IB Account ID (e.g. DU1234567 for paper).',
              condition: isBroker('interactive_brokers'),
            },
          },
          {
            name: 'ibConsumerKeyPlaintext',
            label: 'Consumer Key',
            type: 'text',
            required: false,
            admin: {
              description: 'The 9-character consumer key you chose in IB\'s OAuth self-service portal.',
              condition: isBroker('interactive_brokers'),
            },
            hooks: {
              afterRead: [() => undefined],
            },
          },
          {
            name: 'ibConsumerKeyMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('interactive_brokers'),
              description: 'Your consumer key (last 4 characters only).',
            },
            access: {
              update: () => false,
            },
          },
          {
            name: 'ibAccessTokenPlaintext',
            label: 'Access Token',
            type: 'text',
            required: false,
            admin: {
              description: 'Generated in IB\'s OAuth portal after uploading your public keys.',
              condition: isBroker('interactive_brokers'),
            },
            hooks: {
              afterRead: [() => undefined],
            },
          },
          {
            name: 'ibAccessTokenMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('interactive_brokers'),
              description: 'Your access token (last 4 characters only).',
            },
            access: {
              update: () => false,
            },
          },
          {
            name: 'ibAccessTokenSecretPlaintext',
            label: 'Access Token Secret',
            type: 'text',
            required: false,
            admin: {
              description: 'Generated alongside the access token — shown only once in IB\'s portal, save it then.',
              condition: isBroker('interactive_brokers'),
            },
            hooks: {
              afterRead: [() => undefined],
            },
          },
          {
            name: 'ibAccessTokenSecretMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('interactive_brokers'),
              description: 'Your access token secret (last 4 characters only).',
            },
            access: {
              update: () => false,
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
            name: 'ibDhPrime',
            label: 'Diffie-Hellman Prime (hex)',
            type: 'textarea',
            admin: {
              condition: isBroker('interactive_brokers'),
              description:
                'Hex representation of the prime from your dhparam.pem, extracted via `openssl dhparam -in dhparam.pem -text -noout`. Not secret on its own — this is a public DH parameter — so it is stored as plain text, unlike the fields on the Credentials tab.',
            },
          },
          {
            name: 'ibSignatureKeyPemPlaintext',
            label: 'RSA Signature Private Key (PEM)',
            type: 'textarea',
            required: false,
            admin: {
              condition: isBroker('interactive_brokers'),
              description: 'Paste the full contents of private_signature.pem. Signs every request.',
            },
            hooks: {
              afterRead: [() => undefined],
            },
          },
          {
            name: 'ibSignatureKeyPemMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('interactive_brokers'),
              description: 'Signature key on file (fingerprint only).',
            },
            access: {
              update: () => false,
            },
          },
          {
            name: 'ibEncryptionKeyPemPlaintext',
            label: 'RSA Encryption Private Key (PEM)',
            type: 'textarea',
            required: false,
            admin: {
              condition: isBroker('interactive_brokers'),
              description: 'Paste the full contents of private_encryption.pem. Decrypts the access token secret during login.',
            },
            hooks: {
              afterRead: [() => undefined],
            },
          },
          {
            name: 'ibEncryptionKeyPemMasked',
            type: 'text',
            admin: {
              readOnly: true,
              condition: isBroker('interactive_brokers'),
              description: 'Encryption key on file (fingerprint only).',
            },
            access: {
              update: () => false,
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
  // Encrypted IB OAuth credential storage (hidden). Same AES-256-GCM
  // pattern as apiKey/secretKey above — one (encrypted, iv, authTag) triple
  // per secret field. ibDhPrime is intentionally NOT here: it's a public DH
  // parameter, stored as plain text on the Advanced Settings tab.
  ...(['ibConsumerKey', 'ibAccessToken', 'ibAccessTokenSecret', 'ibSignatureKeyPem', 'ibEncryptionKeyPem'].flatMap(
    (base) => [
      { name: `${base}Encrypted`, type: 'text' as const, admin: { hidden: true } },
      { name: `${base}Iv`, type: 'text' as const, admin: { hidden: true } },
      { name: `${base}AuthTag`, type: 'text' as const, admin: { hidden: true } },
    ],
  )),
  {
    name: 'vaultId',
    type: 'text',
    admin: {
      description: 'Vault ID storing this broker account credentials.',
      hidden: true,
    },
  },
  {
    name: 'credentialId',
    type: 'text',
    admin: {
      description: 'Credential ID inside the vault.',
      hidden: true,
    },
  },
  {
    name: 'vaultSyncStatus',
    type: 'select',
    defaultValue: 'unsynced',
    options: [
      { label: 'Unsynced', value: 'unsynced' },
      { label: 'Synced', value: 'synced' },
      { label: 'Error', value: 'error' },
    ],
    admin: {
      description: 'Sync status of vault credentials.',
    },
  },
];
