import type { Field } from 'payload'

import { SCREENING_CATEGORIES, SCREENING_STATUSES, EXIT_REASONS } from './domain/rules/screeningRules'

export const candidateScreeningsFields: Field[] = [
  // ─── Identity ───────────────────────────────────────────────
  {
    name: 'instrument',
    type: 'relationship',
    relationTo: 'instruments',
    required: true,
    index: true,
  },
  {
    name: 'category',
    type: 'select',
    required: true,
    options: [...SCREENING_CATEGORIES],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Regime Context ─────────────────────────────────────────
  {
    name: 'marketRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Market regime at screening time',
    },
  },
  {
    name: 'sectorRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Sector regime at screening time',
    },
  },

  // ─── Scores at Screening Time ──────────────────────────────
  {
    name: 'compositeScore',
    type: 'number',
    required: true,
    admin: {
      description: 'Hohn/Munger composite conviction score',
    },
  },
  {
    name: 'qgarpScore',
    type: 'number',
  },
  {
    name: 'fcfMargin',
    type: 'number',
  },
  {
    name: 'piotroskiFScore',
    type: 'number',
  },
  {
    name: 'priceToGFValue',
    type: 'number',
    admin: {
      description: 'Price / GF Value ratio (< 1 = undervalued)',
    },
  },
  {
    name: 'guruConviction',
    type: 'number',
  },
  {
    name: 'insiderConviction',
    type: 'number',
  },
  {
    name: 'beneishM',
    type: 'number',
    admin: {
      description: 'Beneish M-Score (> -1.78 = manipulation risk)',
    },
  },
  {
    name: 'altmanZ',
    type: 'number',
    admin: {
      description: 'Altman Z-Score (< 1.81 = distress zone)',
    },
  },

  // ─── Lifecycle ──────────────────────────────────────────────
  {
    name: 'enteredAt',
    type: 'date',
    required: true,
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
      description: 'When this ticker passed the screening filter',
    },
  },
  {
    name: 'exitedAt',
    type: 'date',
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
      description: 'When this ticker stopped passing the filter',
    },
  },
  {
    name: 'exitReason',
    type: 'select',
    options: [...EXIT_REASONS],
  },
  {
    name: 'status',
    type: 'select',
    required: true,
    defaultValue: 'active',
    options: [...SCREENING_STATUSES],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Tenant ─────────────────────────────────────────────────
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    index: true,
    admin: {
      position: 'sidebar',
    },
  },
]
