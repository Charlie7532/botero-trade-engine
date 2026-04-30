import type { AccessArgs } from 'payload'

import type { User } from '@/payload-types'

type CanCreateUser = (args: AccessArgs<User>) => Promise<boolean> | boolean

export const canCreateUser: CanCreateUser = async ({ req }) => {
  if (req.user) return true

  try {
    const siteSettings = await req.payload.findGlobal({ slug: 'site-settings' })
    const settings = siteSettings as unknown as { allowNewUsers?: boolean }
    return settings.allowNewUsers !== false
  } catch {
    // If settings are unavailable, keep registration enabled by default.
    return true
  }
}
