import type { Field } from 'payload'

import { CALIBRATION_CATEGORIES, CALIBRATION_STATUSES } from './domain/rules/calibrationRules'

export const calibrationProfilesFields: Field[] = [
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
    options: [...CALIBRATION_CATEGORIES],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Regime Context (triple FK) ─────────────────────────────
  {
    name: 'marketRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Market-level regime when this calibration was trained',
    },
  },
  {
    name: 'sectorRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Sector-level regime when this calibration was trained',
    },
  },
  {
    name: 'instrumentRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'Instrument-level regime when this calibration was trained',
    },
  },

  // ─── Signal Weights (Oracle Backtest output) ────────────────
  {
    name: 'signals',
    type: 'json',
    required: true,
    admin: {
      description: 'Array of {name, weight, ceiling_sharpe} — calibrated signal weights',
    },
  },
  {
    name: 'compositeSharpe',
    type: 'number',
    admin: {
      description: 'Composite Sharpe ratio of the calibrated strategy',
    },
  },
  {
    name: 'winRate',
    type: 'number',
    admin: {
      description: 'Win rate percentage of the calibrated strategy',
    },
  },
  {
    name: 'totalTrades',
    type: 'number',
    admin: {
      description: 'Number of trades in the calibration backtest',
    },
  },

  // ─── Training Data Range ────────────────────────────────────
  {
    name: 'trainedAt',
    type: 'date',
    required: true,
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
    },
  },
  {
    name: 'dataRangeFrom',
    type: 'date',
    admin: {
      description: 'Start of OHLCV data used for calibration',
    },
  },
  {
    name: 'dataRangeTo',
    type: 'date',
    admin: {
      description: 'End of OHLCV data used for calibration',
    },
  },

  // ─── Warm-Start Chain ───────────────────────────────────────
  {
    name: 'warmStartFrom',
    type: 'relationship',
    relationTo: 'calibration-profiles',
    admin: {
      description: 'Parent calibration used as warm-start (initial weights)',
    },
  },
  {
    name: 'warmStartDelta',
    type: 'json',
    admin: {
      description: 'Diff of signal weights vs parent — shows how much changed',
    },
  },

  // ─── Invalidation ──────────────────────────────────────────
  {
    name: 'status',
    type: 'select',
    required: true,
    defaultValue: 'active',
    options: [...CALIBRATION_STATUSES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'invalidatedBy',
    type: 'relationship',
    relationTo: 'regime-phases',
    admin: {
      description: 'The regime change that invalidated this calibration',
    },
  },
  {
    name: 'invalidatedAt',
    type: 'date',
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
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
