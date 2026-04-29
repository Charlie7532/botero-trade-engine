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
    name: 'nickname',
    type: 'text',
  },
  {
    name: 'preferredLanguage',
    type: 'select',
    defaultValue: 'en',
    options: [
      { label: 'English', value: 'en' },
      { label: 'Espanol', value: 'es' },
    ],
  },
  {
    name: 'authProvider',
    type: 'select',
    defaultValue: 'payload',
    options: [
      { label: 'Payload', value: 'payload' },
      { label: 'Google', value: 'google' },
    ],
    admin: {
      position: 'sidebar',
      readOnly: true,
    },
  },
  {
    name: 'passwordSetAt',
    type: 'date',
    admin: {
      position: 'sidebar',
      readOnly: true,
      date: {
        pickerAppearance: 'dayAndTime',
      },
    },
  },
  {
    name: 'otpCode',
    type: 'text',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'otpExpiry',
    type: 'date',
    admin: {
      hidden: true,
    },
  },
  {
    name: 'otpAttempts',
    type: 'number',
    defaultValue: 0,
    admin: {
      hidden: true,
    },
  },
  {
    name: 'login_count',
    type: 'number',
    defaultValue: 0,
    admin: {
      position: 'sidebar',
      readOnly: true,
    },
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
