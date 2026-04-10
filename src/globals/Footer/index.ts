import type { GlobalConfig } from 'payload'
import { anyone } from '@/access/anyone'
import { footerFields } from './fields'
import { footerLifecycle } from './lifecycle'

export const Footer: GlobalConfig = {
  slug: 'footer',
  access: {
    read: anyone,
  },
  admin: {
    group: 'Settings',
  },
  fields: footerFields,
  hooks: footerLifecycle,
}
