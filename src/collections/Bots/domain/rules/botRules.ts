export const BOT_STATUSES = [
  { label: 'Active', value: 'active' },
  { label: 'Paused', value: 'paused' },
  { label: 'Stopped', value: 'stopped' },
  { label: 'Error', value: 'error' },
] as const

export type BotStatus = 'active' | 'paused' | 'stopped' | 'error'

export const STRATEGY_TYPES = [
  { label: 'QGARP', value: 'qgarp' },
  { label: 'Momentum', value: 'momentum' },
  { label: 'Mean Reversion', value: 'mean_reversion' },
  { label: 'Trend Following', value: 'trend_following' },
  { label: 'Custom', value: 'custom' },
] as const

export type StrategyType = 'qgarp' | 'momentum' | 'mean_reversion' | 'trend_following' | 'custom'
