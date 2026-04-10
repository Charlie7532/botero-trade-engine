import { Field } from 'payload'
import { slugField } from '@/fields/slug'

export const categoriesFields: Field[] = [
  {
    name: 'title',
    type: 'text',
    required: true,
  },
  ...slugField(),
]
