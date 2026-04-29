import type { DashboardConfig } from 'payload'

export const defaultDashboardLayout: NonNullable<DashboardConfig['defaultLayout']> = [
  {
    widgetSlug: 'claude-token-consumption',
    width: 'medium',
  },
  {
    widgetSlug: 'postgres-performance',
    width: 'x-large',
  },
]