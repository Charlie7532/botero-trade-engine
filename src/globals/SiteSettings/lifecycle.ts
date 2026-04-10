import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import { revalidateSiteSettingsState } from '@/modules/layout/application/useCases/revalidateLayoutState'
import type { GlobalAfterChangeHook } from 'payload'

const siteSettingsRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    revalidateSiteSettingsState(cache, payload.logger)
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
