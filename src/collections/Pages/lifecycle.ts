import { handleAfterChangeHook, handleAfterDeleteHook } from '@/shared/handlers'
import { populatePublishedAt } from '../../hooks/populatePublishedAt'
import type { Page } from '../../payload-types'
import { NextCacheRevalidator } from '../../shared/infrastructure/next/NextCacheRevalidator'
import { 
  revalidatePageStateOnUpdate, 
  revalidatePageStateOnDelete 
} from './domain/useCases/revalidatePageState'

const revalidatePageAdapter = handleAfterChangeHook({
  name: 'Pages',
  operation: 'all',
  handler: async ({ doc, previousDoc, req: { payload, context } }) => {
    if (!context.disableRevalidate) {
      const cacheRevalidator = new NextCacheRevalidator()
      revalidatePageStateOnUpdate(
        doc, 
        previousDoc, 
        cacheRevalidator, 
        payload.logger
      )
    }
    return doc
  },
})

const revalidateDeleteAdapter = handleAfterDeleteHook({
  name: 'Pages',
  handler: async ({ doc, req: { context } }) => {
    if (!context.disableRevalidate) {
      const cacheRevalidator = new NextCacheRevalidator()
      revalidatePageStateOnDelete(doc, cacheRevalidator)
    }
    return doc
  },
})

export const pagesLifecycle = {
  beforeChange: [populatePublishedAt],
  afterChange: [revalidatePageAdapter],
  afterDelete: [revalidateDeleteAdapter],
}
