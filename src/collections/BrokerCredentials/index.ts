import type { CollectionConfig } from 'payload'

import { brokerCredentialsAccess } from './access'
import { brokerCredentialsFields } from './fields'
import { brokerCredentialsLifecycle } from './lifecycle'

export const BrokerCredentials: CollectionConfig = {
  slug: 'broker-credentials',
  access: brokerCredentialsAccess,
  admin: {
    group: 'Trading',
    defaultColumns: ['portfolio', 'keyName', 'maskedPreview'],
    useAsTitle: 'keyName',
  },
  hooks: brokerCredentialsLifecycle,
  fields: brokerCredentialsFields,
  timestamps: true,
}
