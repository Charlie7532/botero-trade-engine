import { handleBeforeChangeHook } from '@/shared/handlers'
import { assignDefaultPublishTimestamp } from '@/shared/application/useCases/assignDefaultPublishTimestamp'

export const populatePublishedAt = handleBeforeChangeHook({
  name: 'PublishDate',
  operation: 'all',
  handler: async ({ data, operation, req }) => {
    return assignDefaultPublishTimestamp(data, operation, req.data?.publishedAt)
  },
})
