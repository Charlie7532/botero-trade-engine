/**
 * Regime phase domain rules — Wyckoff market cycle phases.
 * Pure domain logic, no framework imports.
 */

/**
 * The four Wyckoff market cycle phases.
 * Each instrument, sector, and market can independently be in any phase.
 */
export const REGIME_PHASES = [
  { label: 'Accumulation', value: 'accumulation' },
  { label: 'Markup (Bullish)', value: 'markup' },
  { label: 'Distribution', value: 'distribution' },
  { label: 'Markdown (Bearish)', value: 'markdown' },
] as const

/**
 * Three hierarchical levels of regime detection.
 * Market > Sector > Instrument — each tracked independently.
 */
export const REGIME_LEVELS = [
  { label: 'Market (SPY/VIX)', value: 'market' },
  { label: 'Sector (ETF)', value: 'sector' },
  { label: 'Instrument', value: 'instrument' },
] as const
