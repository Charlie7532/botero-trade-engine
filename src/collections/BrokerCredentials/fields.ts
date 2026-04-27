import type { Field } from 'payload'

import { ALL_CREDENTIAL_KEY_OPTIONS } from './domain/rules/credentialRules'

export const brokerCredentialsFields: Field[] = [
  {
    name: 'brokerAccount',
    type: 'relationship',
    relationTo: 'broker-accounts',
    required: true,
    index: true,
  },
  {
    name: 'keyName',
    type: 'select',
    required: true,
    options: [...ALL_CREDENTIAL_KEY_OPTIONS],
  },
  {
    name: 'plaintextValue',
    type: 'text',
    hooks: {
      afterRead: [
        () => undefined,
      ],
    },
  },
  {
    name: 'encryptedValue',
    type: 'text',
    admin: {
      hidden: true,
      readOnly: true,
    },
    access: {
      read: () => false,
    },
  },
  {
    name: 'iv',
    type: 'text',
    admin: {
      hidden: true,
      readOnly: true,
    },
    access: {
      read: () => false,
    },
  },
  {
    name: 'authTag',
    type: 'text',
    admin: {
      hidden: true,
      readOnly: true,
    },
    access: {
      read: () => false,
    },
  },
  {
    name: 'maskedPreview',
    type: 'text',
    admin: {
      readOnly: true,
    },
    access: {
      update: () => false,
    },
  },
]
