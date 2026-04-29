/**
 * Candidate screening domain rules.
 * Pure domain logic, no framework imports.
 */

export const SCREENING_CATEGORIES = [
  { label: 'CORE — Hohn Quality', value: 'core_hohn' },
  { label: 'CORE — Dividend', value: 'core_dividend' },
  { label: 'TACTICAL — Spring', value: 'tactical_spring' },
  { label: 'TACTICAL — Momentum', value: 'tactical_momentum' },
] as const

export const SCREENING_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Expired', value: 'expired' },
  { label: 'Positioned', value: 'positioned' },
  { label: 'Closed', value: 'closed' },
] as const

export const EXIT_REASONS = [
  { label: 'Score Decay', value: 'score_decay' },
  { label: 'Beneish Flag (Earnings Manipulation)', value: 'beneish_flag' },
  { label: 'Altman Distress', value: 'altman_distress' },
  { label: 'Regime Change', value: 'regime_change' },
  { label: 'Manual', value: 'manual' },
  { label: 'Positioned (trade opened)', value: 'positioned' },
  { label: 'Superseded (newer screening)', value: 'superseded' },
] as const
