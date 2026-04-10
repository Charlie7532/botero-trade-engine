import type { GlobalConfig } from 'payload'
import { anyone } from '@/access/anyone'
import { headerFields } from './fields'
import { headerLifecycle } from './lifecycle'

export const Header: GlobalConfig = {
  slug: 'header',
  access: {
    read: anyone,
  },
  admin: {
    group: 'Settings',
  },
  fields: headerFields,
  hooks: headerLifecycle,
}
