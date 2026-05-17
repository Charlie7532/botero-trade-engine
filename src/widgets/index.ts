import type { DashboardConfig } from 'payload'

import { defaultDashboardLayout } from './defaultLayout'

export const dashboardWidgets: DashboardConfig['widgets'] = [
  {
    slug: 'claude-token-consumption',
    label: 'Claude Token Consumption',
    Component: '@/widgets/ClaudeTokenConsumption',
    minWidth: 'small',
    maxWidth: 'full',
  },
  {
    slug: 'claude-token-breakdown',
    label: 'Claude Token Breakdown',
    Component: '@/widgets/ClaudeTokenBreakdown',
    minWidth: 'small',
    maxWidth: 'full',
  },
  {
    slug: 'neon-cpu',
    label: 'Neon CPU',
    Component: '@/widgets/NeonCpu',
    minWidth: 'small',
    maxWidth: 'medium',
  },
  {
    slug: 'neon-cache',
    label: 'Neon Working Set',
    Component: '@/widgets/NeonCache',
    minWidth: 'small',
    maxWidth: 'medium',
  },
  {
    slug: 'postgres-connections',
    label: 'Postgres Connections',
    Component: '@/widgets/PostgresConnections',
    minWidth: 'small',
    maxWidth: 'medium',
  },
  {
    slug: 'pooler-connections',
    label: 'Pooler Connections',
    Component: '@/widgets/PoolerConnections',
    minWidth: 'small',
    maxWidth: 'medium',
  },
]

export const dashboardConfig: DashboardConfig = {
  widgets: dashboardWidgets,
  defaultLayout: defaultDashboardLayout,
}