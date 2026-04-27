import type { Access, FieldAccess } from 'payload'

import type { User } from '@/payload-types'

export const isSuperAdmin: Access = ({ req: { user } }) => {
  return Boolean((user as User | null)?.role === 'superadmin')
}

export const isSuperAdminFieldLevel: FieldAccess<User> = ({ req: { user } }) => {
  return Boolean(user?.role === 'superadmin')
}