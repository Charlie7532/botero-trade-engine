import type { DashboardConfig } from 'payload'

export const defaultDashboardLayout: NonNullable<DashboardConfig['defaultLayout']> = [
  {
    widgetSlug: 'claude-token-consumption',
    width: 'full',
  },
  {
    widgetSlug: 'claude-token-breakdown',
    width: 'medium',
  },
  {
    widgetSlug: 'neon-cpu',
    width: 'medium',
  },
  {
    widgetSlug: 'neon-cache',
    width: 'medium',
  },
  {
    widgetSlug: 'postgres-connections',
    width: 'medium',
  },
  {
    widgetSlug: 'pooler-connections',
    width: 'medium',
  },
]