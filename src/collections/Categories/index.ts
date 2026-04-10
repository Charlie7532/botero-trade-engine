import type { CollectionConfig } from 'payload'

import { anyone } from '../../access/anyone'
import { authenticated } from '../../access/authenticated'
import { categoriesFields } from './fields'
import { categoriesLifecycle } from './lifecycle'

export const Categories: CollectionConfig = {
  slug: 'categories',
  access: {
    create: authenticated,
    delete: authenticated,
    read: anyone,
    update: authenticated,
  },
  admin: {
    group: 'Website',
    useAsTitle: 'title',
  },
  fields: categoriesFields,
  hooks: categoriesLifecycle,
}
