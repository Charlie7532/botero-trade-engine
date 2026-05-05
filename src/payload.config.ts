// storage-adapter-import-placeholder
import { vercelPostgresAdapter } from '@payloadcms/db-vercel-postgres'
import { vercelBlobStorage } from '@payloadcms/storage-vercel-blob'

import sharp from 'sharp' // sharp-import
import path from 'path'
import { buildConfig, PayloadRequest } from 'payload'
import { fileURLToPath } from 'url'

import { Media } from './collections/Media/index'
import { Users } from './collections/Users/index'
import { Portfolios } from './collections/Portfolios/index'
import { PortfolioMemberships } from './collections/PortfolioMemberships/index'
import { BrokerAccounts } from './collections/BrokerAccounts/index'
import { Bots } from './collections/Bots/index'
import { BotAssignments } from './collections/BotAssignments/index'
import { McpServers } from './collections/McpServers/index'
import { AgentSkills } from './collections/AgentSkills/index'
import { Instruments } from './collections/Instruments'
import { RegimePhases } from './collections/RegimePhases'
import { CalibrationProfiles } from './collections/CalibrationProfiles'
import { CandidateScreenings } from './collections/CandidateScreenings'
import { TradeSnapshots } from './collections/TradeSnapshots'
import { ProjectVaults } from './collections/ProjectVaults'
import { SiteSettings } from './globals/SiteSettings/index'
import { plugins } from './plugins'
import { dashboardConfig } from './widgets'
import { defaultLexical } from '@/fields/defaultLexical'
import { getServerSideURL } from './utilities/getURL'
import brevoAdapter from './utilities/brevoAdapter'
import { UserAvatar } from './collections/Users/avatar'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

export default buildConfig({
  admin: {
    avatar: { Component: '@/components/Admin/PayloadAdminAvatar', },
    components: {
      providers: ['@/components/Admin/AdminHeroUIProvider'],
      logout: { Button: '@/components/Admin/EmptyLogoutButton', },
      // Custom button with site logo at the top of sidebar navigation
      beforeNavLinks: [
        '@/components/SidebarHomeButton'
      ],
      // The `BeforeLogin` component renders a message that you see while logging into your admin panel.
      // Feel free to delete this at any time. Simply remove the line below and the import `BeforeLogin` statement on line 15.
      beforeLogin: [
        // '@/components/BeforeLogin',
        // '@/components/AdminFavicon'
      ],
      // The `BeforeDashboard` component renders the 'welcome' block that you see after logging into your admin panel.
      // Feel free to delete this at any time. Simply remove the line below and the import `BeforeDashboard` statement on line 15.
      beforeDashboard: [
        // '@/components/BeforeDashboard',
      ],
      graphics: {
        Logo: '@/components/Logo/AppLogoExpanded',
        Icon: '@/components/Logo/AppLogoCompact ',
      },
    },
    meta: {
      titleSuffix: '- Main 12 Admin Panel',
    },
    importMap: {
      baseDir: path.resolve(dirname),
    },
    routes: {
      login: '/login',
    },
    dashboard: dashboardConfig,
    user: Users.slug,
    livePreview: {
      breakpoints: [
        {
          label: 'Mobile',
          name: 'mobile',
          width: 375,
          height: 667,
        },
        {
          label: 'Tablet',
          name: 'tablet',
          width: 768,
          height: 1024,
        },
        {
          label: 'Desktop',
          name: 'desktop',
          width: 1440,
          height: 900,
        },
      ],
    },
  },
  email: brevoAdapter(),
  // This config helps us configure global or default features that the other editors can inherit
  editor: defaultLexical,
  db: vercelPostgresAdapter({
    schemaName: 'payload',
    pool: { connectionString: process.env.POSTGRES_URL || '', },
  }),
  collections: [
    // Content
    Media,
    // Users
    Users, UserAvatar,
    // Multi-Tenant Trading
    Portfolios, PortfolioMemberships, BrokerAccounts,
    // AI Agent Resources (must be before Bots — Bots references these)
    McpServers, AgentSkills,
    // Bots & Assignments
    Bots, BotAssignments,
    // Trading Engine — Lifecycle & Calibration
    Instruments, RegimePhases, CalibrationProfiles, CandidateScreenings, TradeSnapshots,
    // Credential Vault
    ProjectVaults,
  ],
  cors: [getServerSideURL()].filter(Boolean),
  globals: [SiteSettings],
  plugins: [
    ...plugins,
    vercelBlobStorage({
      collections: {
        media: {
          prefix: process.env.PROJECT_ID ? `${process.env.PROJECT_ID}/media` : 'media',
        },
        'user-avatar': {
          prefix: process.env.PROJECT_ID ? `${process.env.PROJECT_ID}/avatars` : 'avatars',
        },
      },
      token: process.env.BLOB_READ_WRITE_TOKEN,
    }),
    // storage-adapter-placeholder
  ],
  secret: process.env.PAYLOAD_SECRET,
  sharp,
  typescript: {
    outputFile: path.resolve(dirname, 'payload-types.ts'),
  },
  jobs: {
    access: {
      run: ({ req }: { req: PayloadRequest }): boolean => {
        // Allow logged in users to execute this endpoint (default)
        if (req.user) return true

        // If there is no logged in user, then check
        // for the Vercel Cron secret to be present as an
        // Authorization header:
        const authHeader = req.headers.get('authorization')
        return authHeader === `Bearer ${process.env.CRON_SECRET}`
      },
    },
    tasks: [],
  },
})
