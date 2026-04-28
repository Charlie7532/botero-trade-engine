/**
 * Trade snapshot domain rules.
 * Pure domain logic, no framework imports.
 */

export const TRADE_SIDES = [
  { label: 'Long', value: 'long' },
  { label: 'Short', value: 'short' },
] as const

export const TRADE_STRATEGIES = [
  { label: 'CORE (Hohn/Munger)', value: 'core' },
  { label: 'TACTICAL (Eifert/PTJ)', value: 'tactical' },
] as const

export const TRADE_EXIT_REASONS = [
  { label: 'Target Hit', value: 'target_hit' },
  { label: 'Stop Hit', value: 'stop_hit' },
  { label: 'Manual Exit', value: 'manual' },
  { label: 'Thesis Broke', value: 'thesis_broke' },
  { label: 'Time Decay', value: 'time_decay' },
  { label: 'Regime Change', value: 'regime_change' },
] as const
