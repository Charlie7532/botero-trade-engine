export const BOT_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Paused', value: 'paused' },
  { label: 'Stopped', value: 'stopped' },
  { label: 'Error', value: 'error' },
] as const

export type BotStatus = 'active' | 'paused' | 'stopped' | 'error'

export const STRATEGY_TYPES = [
  // Quality Department (Hohn & Munger — 80%)
  { label: 'Quality: Value', value: 'quality_value' },
  { label: 'Quality: Growth', value: 'quality_growth' },
  { label: 'Quality: Dividend', value: 'quality_dividend' },
  // Speculative Department (Eifert & PTJ — 20%)
  { label: 'Speculative: Momentum', value: 'speculative_momentum' },
  { label: 'Speculative: Gamma', value: 'speculative_gamma' },
  { label: 'Speculative: Breakout', value: 'speculative_breakout' },
  { label: 'Speculative: Spring', value: 'speculative_spring' },
  // Legacy
  { label: 'Custom', value: 'custom' },
] as const

export type StrategyType =
  | 'quality_value'
  | 'quality_growth'
  | 'quality_dividend'
  | 'speculative_momentum'
  | 'speculative_gamma'
  | 'speculative_breakout'
  | 'speculative_spring'
  | 'custom'
