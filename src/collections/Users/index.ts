import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { usersLifecycle } from './lifecycle'
import { usersFields } from './fields'

export const Users: CollectionConfig = {
  slug: 'users',
  access: {
    admin: authenticated,
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Accounts',
    defaultColumns: ['name', 'email'],
    useAsTitle: 'name',
  },
  auth: true,
  hooks: usersLifecycle,
  fields: usersFields,
  timestamps: true,
}