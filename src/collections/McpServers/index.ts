import type { CollectionConfig } from 'payload'

import { isAdmin } from '@/access'
import { mcpServersFields } from './fields'

export const McpServers: CollectionConfig = {
  slug: 'mcp-servers',
  access: {
    create: isAdmin,
    read: isAdmin,
    update: isAdmin,
    delete: isAdmin,
  },
  admin: {
    group: 'System',
    defaultColumns: ['name', 'type', 'category', 'isActive'],
    useAsTitle: 'name',
  },
  hooks: {
    beforeChange: [
      ({ data }) => {
        if (data?.name && !data.slug) {
          data.slug = data.name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '')
        }
        return data
      },
    ],
  },
  fields: mcpServersFields,
  timestamps: true,
}
