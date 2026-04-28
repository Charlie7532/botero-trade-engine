import type { Field } from 'payload'

import { REGIME_PHASES, REGIME_LEVELS } from './domain/rules/regimeRules'

export const regimePhasesFields: Field[] = [
  // ─── Identity ───────────────────────────────────────────────
  {
    name: 'instrument',
    type: 'relationship',
    relationTo: 'instruments',
    required: true,
    index: true,
    admin: {
      description: 'Instrument this phase belongs to (SPY for market, XLK for sector, AAPL for instrument)',
    },
  },
  {
    name: 'level',
    type: 'select',
    required: true,
    options: [...REGIME_LEVELS],
    index: true,
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'phase',
    type: 'select',
    required: true,
    options: [...REGIME_PHASES],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Lifecycle ──────────────────────────────────────────────
  {
    name: 'detectedAt',
    type: 'date',
    required: true,
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
      description: 'When this phase transition was detected',
    },
  },
  {
    name: 'closedAt',
    type: 'date',
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
      description: 'When this phase ended (null = currently active)',
    },
  },
  {
    name: 'durationDays',
    type: 'number',
    admin: {
      description: 'Duration in days (calculated when phase closes)',
      readOnly: true,
    },
  },

  // ─── Detection Context ─────────────────────────────────────
  {
    name: 'vixAtDetection',
    type: 'number',
    admin: {
      description: 'VIX level when phase was detected',
    },
  },
  {
    name: 'breadthAtDetection',
    type: 'number',
    admin: {
      description: '% of stocks above 50-DMA at detection',
    },
  },
  {
    name: 'relativeVolumeAtDetection',
    type: 'number',
    admin: {
      description: 'Relative volume at detection time',
    },
  },
  {
    name: 'triggerSignal',
    type: 'text',
    admin: {
      description: 'What signal triggered the phase change (e.g., CHoCH_BULLISH, VIX_CROSSOVER_25)',
    },
  },

  // ─── History Chain ──────────────────────────────────────────
  {
    name: 'previousPhase',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Previous phase in the chain (for historical tracking)',
    },
  },
]
