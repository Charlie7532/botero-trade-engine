import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access/authenticated'
import { infraSnapshotsFields } from './fields'
import { captureSnapshotEndpoint } from './interface/endpoints/captureSnapshotEndpoint'

export const InfraSnapshots: CollectionConfig = {
  slug: 'infra-snapshots',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Infrastructure',
    defaultColumns: ['capturedAt', 'cpuUsedSec', 'activeBackends', 'poolerActive', 'deadlocks'],
    useAsTitle: 'capturedAt',
    hidden: false,
  },
  endpoints: [captureSnapshotEndpoint],
  fields: infraSnapshotsFields,
  indexes: [{ fields: ['capturedAt'] }],
  timestamps: true,
}
