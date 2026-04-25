import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import type { GlobalAfterChangeHook } from 'payload'

const siteSettingsRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    payload.logger.info(`Revalidating site-settings`)
    cache.revalidateTag('global_site-settings')
  }
  return doc
}

export const siteSettingsLifecycle = {
  afterChange: [
    handleGlobalAfterChangeHook({
      name: 'SiteSettings',
      handler: siteSettingsRevalidationAdapter,
    }),
  ],
}
