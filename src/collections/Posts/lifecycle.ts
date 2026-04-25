import { handleAfterChangeHook, handleAfterDeleteHook, handleAfterReadHook } from '@/shared/handlers'

import type { Post } from '../../payload-types'
import { NextCacheRevalidator } from '../../shared/infrastructure/next/NextCacheRevalidator'
import { PayloadUserRepository } from './infrastructure/PayloadUserRepository'
import { populatePublicAuthors } from './domain/useCases/populatePublicAuthors'
import { 
  revalidatePostStateOnUpdate, 
  revalidatePostStateOnDelete 
} from './domain/useCases/revalidatePostState'

const populateAuthorsAdapter = handleAfterReadHook({
  name: 'Posts',
  handler: async ({ doc, req: { payload } }) => {
    if (doc?.authors && doc?.authors?.length > 0) {
      const userRepository = new PayloadUserRepository(payload)
      const populatedAuthors = await populatePublicAuthors(doc.authors, userRepository)
      
      if (populatedAuthors.length > 0) {
        doc.populatedAuthors = populatedAuthors
      }
    }
    return doc
  },
})

const revalidatePostAdapter = handleAfterChangeHook({
  name: 'Posts',
  operation: 'all',
  handler: async ({ doc, previousDoc, req: { payload, context } }) => {
    if (!context.disableRevalidate) {
      const cacheRevalidator = new NextCacheRevalidator()
      revalidatePostStateOnUpdate(
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
  name: 'Posts',
  handler: async ({ doc, req: { context } }) => {
    if (!context.disableRevalidate) {
      const cacheRevalidator = new NextCacheRevalidator()
      revalidatePostStateOnDelete(doc, cacheRevalidator)
    }
    return doc
  },
})

export const postsLifecycle = {
  afterChange: [revalidatePostAdapter],
  afterRead: [populateAuthorsAdapter],
  afterDelete: [revalidateDeleteAdapter],
}
