import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import type { GlobalAfterChangeHook } from 'payload'

const headerRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    payload.logger.info(`Revalidating header`)
    cache.revalidateTag('global_header')
  }
  return doc
}

export const headerLifecycle = {
  afterChange: [
    handleGlobalAfterChangeHook({
      name: 'Header',
      handler: headerRevalidationAdapter,
    }),
  ],
}
