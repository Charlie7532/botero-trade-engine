import type { Field } from 'payload'

import { TRADE_SIDES, TRADE_STRATEGIES, TRADE_EXIT_REASONS } from './domain/rules/tradeRules'

export const tradeSnapshotsFields: Field[] = [
  // ─── Identity & Relationships ──────────────────────────────
  {
    name: 'instrument',
    type: 'relationship',
    relationTo: 'instruments',
    required: true,
    index: true,
  },
  {
    name: 'screening',
    type: 'relationship',
    relationTo: 'candidate-screenings',
    admin: {
      description: 'Candidate screening that originated this trade evaluation',
    },
  },
  {
    name: 'calibration',
    type: 'relationship',
    relationTo: 'calibration-profiles',
    admin: {
      description: 'Calibration profile used for signal weights',
    },
  },

  // ─── Regime Context (triple FK) ─────────────────────────────
  {
    name: 'marketRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
  },
  {
    name: 'sectorRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
  },
  {
    name: 'instrumentRegime',
    type: 'relationship',
    relationTo: 'regime-phases',
  },

  // ─── Gate Result ────────────────────────────────────────────
  {
    name: 'gateApproved',
    type: 'checkbox',
    defaultValue: false,
    admin: {
      description: 'Whether the PreTradeGate approved this trade',
      position: 'sidebar',
    },
  },
  {
    name: 'gateReason',
    type: 'text',
    admin: {
      description: 'Reason for gate approval/rejection',
    },
  },
  {
    name: 'compositeScore',
    type: 'number',
  },

  // ─── Signal State ───────────────────────────────────────────
  {
    name: 'signals',
    type: 'json',
    admin: {
      description: 'Snapshot of all signal values at evaluation time',
    },
  },
  {
    name: 'structureResult',
    type: 'json',
    admin: {
      description: 'SMC analysis result (BOS, CHoCH, OB, FVG)',
    },
  },

  // ─── Execution Intent ──────────────────────────────────────
  {
    name: 'side',
    type: 'select',
    options: [...TRADE_SIDES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'strategy',
    type: 'select',
    options: [...TRADE_STRATEGIES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'entryPrice',
    type: 'number',
  },
  {
    name: 'stopPrice',
    type: 'number',
  },
  {
    name: 'targetPrice',
    type: 'number',
  },

  // ─── Outcome (filled post-trade) ──────────────────────────
  {
    name: 'exitPrice',
    type: 'number',
  },
  {
    name: 'exitReason',
    type: 'select',
    options: [...TRADE_EXIT_REASONS],
  },
  {
    name: 'pnlPct',
    type: 'number',
    admin: {
      description: 'Profit/Loss percentage',
    },
  },
  {
    name: 'openedAt',
    type: 'date',
    admin: {
      date: { pickerAppearance: 'dayAndTime' },
    },
  },
  {
    name: 'closedAt',
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
