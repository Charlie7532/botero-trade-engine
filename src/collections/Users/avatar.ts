import type { CollectionConfig } from 'payload'

import path from 'path'
import { fileURLToPath } from 'url'

import { anyone } from '@/access/anyone'
import { authenticated } from '@/access/authenticated'
import { isSelfOrAdmin } from '@/access/isSelfOrAdmin'
import { userAvatarFields } from './fields'
import { userAvatarLifecycle } from './lifecycle'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

export const UserAvatar: CollectionConfig = {
  slug: 'user-avatar',
  access: {
    create: authenticated,
    read: anyone,
    update: isSelfOrAdmin(),
    delete: isSelfOrAdmin(),
  },
  admin: {
    group: 'Users',
    hidden: true,
    description: 'User profile avatars and profile pictures',
  },
  hooks: userAvatarLifecycle,
  fields: userAvatarFields,
  upload: {
    staticDir: path.resolve(dirname, '../../../public/avatars'),
    adminThumbnail: 'thumbnail',
    focalPoint: true,
    imageSizes: [
      {
        name: 'thumbnail',
        width: 100,
        height: 100,
      },
      {
        name: 'small',
        width: 200,
        height: 200,
      },
      {
        name: 'medium',
        width: 400,
        height: 400,
      },
    ],
    mimeTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
  },
}
