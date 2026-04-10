import { handleAfterChangeHook } from '@/shared/handlers'
import { NextCacheRevalidator } from '@/shared/infrastructure/next/NextCacheRevalidator'
import { revalidateRedirectsState } from '@/shared/application/useCases/revalidateRedirectsState'

export const revalidateRedirects = handleAfterChangeHook({
  name: 'Redirects',
  handler: async ({ doc, req: { payload } }) => {
    payload.logger.info(`Revalidating redirects`)

    const cacheRevalidator = new NextCacheRevalidator()
    revalidateRedirectsState(cacheRevalidator)

    return doc
  },
})


