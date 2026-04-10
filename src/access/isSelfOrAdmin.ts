import type { Access } from 'payload'

type IsSelfOrAdminOptions = {
  selfField?: string
  adminRoles?: string[]
}

export const isSelfOrAdmin = ({
  selfField = 'user',
  adminRoles = ['admin', 'superadmin'],
}: IsSelfOrAdminOptions = {}): Access => {
  return ({ req: { user } }) => {
    if (!user) return false

    const role = (user as { role?: string }).role
    if (role && adminRoles.includes(role)) {
      return true
    }

    return {
      [selfField]: {
        equals: user.id,
      },
    }
  }
}