import { handleBeforeChangeHook } from '@/shared/handlers'
import { assignInitialAdminRole } from '../../modules/users/application/useCases/assignInitialAdminRole'
import { formatUserAvatarUpload } from '../../modules/users/application/useCases/formatUserAvatarUpload'

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
    return formatUserAvatarUpload(data, req, operation)
  },
})

export const userAvatarLifecycle = {
  beforeChange: [formatAvatarData],
}
