import type { CollectionConfig } from 'payload'
import { projectVaultsFields } from './fields'
import { isAdmin } from '@/access'

export const ProjectVaults: CollectionConfig = {
  slug: 'project-vaults',
  admin: {
    group: 'System',
    defaultColumns: ['name', 'status', 'lastSyncedAt'],
    useAsTitle: 'name',
  },
  access: {
    create: isAdmin,
    read: isAdmin,
    update: isAdmin,
    delete: isAdmin,
  },
  fields: projectVaultsFields,
  timestamps: true,
}
