import { handleGlobalAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import { revalidateHeaderState } from '@/modules/layout/application/useCases/revalidateLayoutState'
import type { GlobalAfterChangeHook } from 'payload'

const headerRevalidationAdapter: GlobalAfterChangeHook = ({ doc, req: { payload, context } }) => {
  if (!context.disableRevalidate) {
    const cache = new NextCacheRevalidator()
    revalidateHeaderState(cache, payload.logger)
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
