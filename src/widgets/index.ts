import type { DashboardConfig } from 'payload'

import { defaultDashboardLayout } from './defaultLayout'

export const dashboardWidgets: DashboardConfig['widgets'] = [
  {
    slug: 'claude-token-consumption',
    label: 'Claude Token Consumption',
    ComponentPath: '@/widgets/ClaudeTokenConsumptionWidget',
    minWidth: 'small',
    maxWidth: 'large',
  },
  {
    slug: 'postgres-performance',
    label: 'Postgres Performance',
    ComponentPath: '@/widgets/PostgresPerformanceWidget',
    minWidth: 'large',
    maxWidth: 'full',
  },
]

export const dashboardConfig: DashboardConfig = {
  widgets: dashboardWidgets,
  defaultLayout: defaultDashboardLayout,
}