import type { GlobalConfig } from 'payload'
import { anyone } from '@/access/anyone'
import { siteSettingsFields } from './fields'
import { siteSettingsLifecycle } from './lifecycle'

export const SiteSettings: GlobalConfig = {
  slug: 'site-settings',
  access: {
    read: anyone,
  },
  admin: {
    group: 'Settings',
  },
  fields: siteSettingsFields,
  hooks: siteSettingsLifecycle,
}
