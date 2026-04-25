import { handleBeforeChangeHook } from '@/shared/handlers'
import { assignInitialAdminRole } from './domain/useCases/assignInitialAdminRole'
import type { PayloadRequest } from 'payload'

const ensureFirstUserIsSuperAdmin = handleBeforeChangeHook({
  name: 'Users',
  operation: 'create',
  handler: async ({ data, req }) => {
    const { totalDocs } = await req.payload.count({
      collection: 'users',
      where: {},
    })

    return assignInitialAdminRole(data, totalDocs)
  },
})

export const usersLifecycle = {
  beforeChange: [ensureFirstUserIsSuperAdmin],
}

const formatAvatarData = handleBeforeChangeHook({
  name: 'UserAvatar',
  operation: 'all',
  handler: async ({ data, req, operation }) => {
    // Bind owner on create, but do not reassign owner on updates.
    if (operation === 'create' && req.user && !data.user) {
      data.user = req.user.id
    }

    // Auto-generate alt text if not provided
    if (!data.alt) {
      const user = req?.user
      const userName = user?.name || user?.email || 'user'
      data.alt = `${userName} - avatar`
    }

    return data
  },
})

export const userAvatarLifecycle = {
  beforeChange: [formatAvatarData],
}
