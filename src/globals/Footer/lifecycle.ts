import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import { revalidateFooterState } from '@/modules/layout/application/useCases/revalidateLayoutState'
import type { GlobalAfterChangeHook } from 'payload'

const footerRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    revalidateFooterState(cache, payload.logger)
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
