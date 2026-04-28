/**
 * Calibration profile domain rules.
 * Pure domain logic, no framework imports.
 */

export const CALIBRATION_CATEGORIES = [
  { label: 'CORE — Hohn Quality', value: 'core_hohn' },
  { label: 'CORE — Dividend', value: 'core_dividend' },
  { label: 'TACTICAL — Spring', value: 'tactical_spring' },
  { label: 'TACTICAL — Momentum', value: 'tactical_momentum' },
] as const

export const CALIBRATION_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Superseded (newer version)', value: 'superseded' },
  { label: 'Invalidated (regime changed)', value: 'invalidated' },
] as const
