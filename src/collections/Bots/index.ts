import type { CollectionConfig } from 'payload'

import { isPortfolioMember, isPortfolioAdmin } from '@/access'
import { getServerSideURL } from '@/utilities/getURL'
import { botsFields } from './fields'
import { botsLifecycle } from './lifecycle'

function agentChatUrl(doc: Record<string, unknown>): string {
  const slug = doc?.botSlug as string | undefined
  if (!slug || doc?.executionType !== 'agent') return ''
  return `${getServerSideURL()}/agent/${slug}`
}

export const Bots: CollectionConfig = {
  slug: 'bots',
  access: {
    create: isPortfolioAdmin(),
    read: isPortfolioMember(),
    update: isPortfolioAdmin(),
    delete: isPortfolioAdmin(),
  },
  admin: {
    group: 'Accounts',
    defaultColumns: ['name', 'portfolio', 'executionType', 'strategyType', 'status'],
    useAsTitle: 'name',
    // "Open in new tab" button
    preview: (doc) => agentChatUrl(doc as Record<string, unknown>) || null,
    // Live preview iframe inside admin panel
    livePreview: {
      url: ({ data }) => agentChatUrl(data),
    },
  },
  hooks: botsLifecycle,
  fields: botsFields,
  timestamps: true,
}
