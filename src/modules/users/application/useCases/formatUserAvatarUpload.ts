import type { PayloadRequest } from 'payload'

export function formatUserAvatarUpload(data: any, req: PayloadRequest, operation: string) {
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
}
