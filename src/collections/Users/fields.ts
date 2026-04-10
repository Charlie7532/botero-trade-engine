import { Field } from 'payload'
import { isAdminFieldLevel } from '@/access'

export const ROLES = [
  {
    label: 'Super Admin',
    value: 'superadmin',
  },
  {
    label: 'Admin',
    value: 'admin',
  },
  {
    label: 'User',
    value: 'user',
  },
]

export const usersFields: Field[] = [
  {
    name: 'name',
    type: 'text',
  },
  {
    name: 'avatar',
    type: 'upload',
    relationTo: 'user-avatar',
    label: 'Avatar',
    admin: {
      position: 'sidebar',
      components: {
        Cell: '@/collections/Users/components/UserAvatarCell#UserAvatarCell',
      },
    },
  },
  {
    name: 'role',
    type: 'select',
    required: true,
    defaultValue: 'user',
    options: ROLES,
    access: {
      update: isAdminFieldLevel,
    },
    admin: {
      position: 'sidebar',
    },
  },
]

export const userAvatarFields: Field[] = [
  {
    name: 'alt',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'user',
    type: 'relationship',
    relationTo: 'users',
    required: true,
    unique: true,
    index: true,
    admin: {
      hidden: true,
      readOnly: true,
    },
  },
]
