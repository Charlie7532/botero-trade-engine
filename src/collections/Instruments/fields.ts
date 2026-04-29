import type { Field } from 'payload'

import {
  INSTRUMENT_TYPES,
  UNIVERSES,
  CYCLICAL_TYPES,
  MARKET_CAPS,
  GICS_SECTORS,
} from './domain/rules/instrumentRules'

export const instrumentsFields: Field[] = [
  // ─── Identity ───────────────────────────────────────────────
  {
    name: 'ticker',
    type: 'text',
    required: true,
    unique: true,
    index: true,
    admin: {
      description: 'Ticker symbol (e.g., AAPL, XLK, SPY)',
    },
  },
  {
    name: 'name',
    type: 'text',
    required: true,
    admin: {
      description: 'Full instrument name',
    },
  },
  {
    name: 'instrumentType',
    type: 'select',
    required: true,
    options: [...INSTRUMENT_TYPES],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── GICS Taxonomy ──────────────────────────────────────────
  {
    name: 'gicsSector',
    type: 'select',
    options: [...GICS_SECTORS],
    admin: {
      description: 'GICS sector classification',
    },
  },
  {
    name: 'gicsIndustry',
    type: 'text',
    admin: {
      description: 'GICS industry (e.g., Semiconductors)',
    },
  },
  {
    name: 'gicsSubIndustry',
    type: 'text',
    admin: {
      description: 'GICS sub-industry (e.g., Semiconductor Equipment)',
    },
  },

  // ─── Classification ─────────────────────────────────────────
  {
    name: 'sectorETF',
    type: 'relationship',
    relationTo: 'instruments',
    admin: {
      description: 'Parent sector ETF (e.g., AAPL → XLK)',
    },
  },
  {
    name: 'universe',
    type: 'select',
    options: [...UNIVERSES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'cyclicalType',
    type: 'select',
    options: [...CYCLICAL_TYPES],
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'marketCap',
    type: 'select',
    options: [...MARKET_CAPS],
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Status Flags ───────────────────────────────────────────
  {
    name: 'isActive',
    type: 'checkbox',
    defaultValue: true,
    admin: {
      position: 'sidebar',
    },
  },
  {
    name: 'isInSP500',
    type: 'checkbox',
    defaultValue: false,
    admin: {
      position: 'sidebar',
    },
  },

  // ─── Fundamental Snapshot (refreshed by scanner) ────────────
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Fundamentals',
        fields: [
          {
            name: 'lastFundamentals',
            type: 'json',
            admin: {
              description: 'Latest fundamental metrics (QGARP, Piotroski, Altman Z, FCF Margin, etc.)',
            },
          },
          {
            name: 'fundamentalsUpdatedAt',
            type: 'date',
            admin: {
              date: { pickerAppearance: 'dayAndTime' },
              description: 'When fundamentals were last refreshed',
            },
          },
          {
            name: 'nextEarningsDate',
            type: 'date',
            admin: {
              description: 'Next earnings report date — triggers fundamental refresh',
            },
          },
        ],
      },
      {
        label: 'Regime Phases',
        fields: [
          {
            name: 'regimePhases',
            type: 'join',
            collection: 'regime-phases',
            on: 'instrument',
          },
        ],
      },
      {
        label: 'Screenings',
        fields: [
          {
            name: 'screenings',
            type: 'join',
            collection: 'candidate-screenings',
            on: 'instrument',
          },
        ],
      },
      {
        label: 'Calibrations',
        fields: [
          {
            name: 'calibrations',
            type: 'join',
            collection: 'calibration-profiles',
            on: 'instrument',
          },
        ],
      },
    ],
  },

  // ─── Tenant ─────────────────────────────────────────────────
  {
    name: 'portfolio',
    type: 'relationship',
    relationTo: 'portfolios',
    index: true,
    admin: {
      position: 'sidebar',
      description: 'Owning portfolio (tenant)',
    },
  },
]
