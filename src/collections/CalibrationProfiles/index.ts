import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { calibrationProfilesFields } from './fields'

export const CalibrationProfiles: CollectionConfig = {
  slug: 'calibration-profiles',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Trading Engine',
    defaultColumns: ['instrument', 'category', 'status', 'compositeSharpe', 'trainedAt'],
    useAsTitle: 'category',
  },
  fields: calibrationProfilesFields,
  timestamps: true,
}
