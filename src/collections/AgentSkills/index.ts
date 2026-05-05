import type { CollectionConfig } from 'payload'

import { isAdmin } from '@/access'
import { agentSkillsFields } from './fields'
import { resyncDependentBotsOnSkillChange } from './infrastructure/hooks/resyncDependentBotsOnSkillChange'

export const AgentSkills: CollectionConfig = {
  slug: 'agent-skills',
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
    afterChange: [resyncDependentBotsOnSkillChange],
  },
  fields: agentSkillsFields,
  timestamps: true,
}
