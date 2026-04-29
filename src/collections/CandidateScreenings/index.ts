import type { CollectionConfig } from 'payload'

import { authenticated } from '@/access'
import { candidateScreeningsFields } from './fields'

export const CandidateScreenings: CollectionConfig = {
  slug: 'candidate-screenings',
  access: {
    create: authenticated,
    read: authenticated,
    update: authenticated,
    delete: authenticated,
  },
  admin: {
    group: 'Trading Engine',
    defaultColumns: ['instrument', 'category', 'compositeScore', 'status', 'enteredAt'],
    useAsTitle: 'category',
  },
  fields: candidateScreeningsFields,
  timestamps: true,
}
