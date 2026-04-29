import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { tradeSnapshotsFields } from './fields'

export const TradeSnapshots: CollectionConfig = {
  slug: 'trade-snapshots',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Trading Engine',
    defaultColumns: ['instrument', 'strategy', 'gateApproved', 'side', 'pnlPct', 'openedAt'],
    useAsTitle: 'strategy',
  },
  fields: tradeSnapshotsFields,
  timestamps: true,
}
