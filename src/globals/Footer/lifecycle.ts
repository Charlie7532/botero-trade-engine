import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import type { GlobalAfterChangeHook } from 'payload'

const footerRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    payload.logger.info(`Revalidating footer`)
    cache.revalidateTag('global_footer')
  }
  return doc
}

export const footerLifecycle = {
  afterChange: [
    handleGlobalAfterChangeHook({
      name: 'Footer',
      handler: footerRevalidationAdapter,
    }),
  ],
}
