import { mcpPlugin } from '@payloadcms/plugin-mcp'

import { mcpCollections } from './collections'

/**
 * Private (admin / internal) Payload MCP plugin instance.
 *
 * Endpoint: `POST /api/mcp` (set by the plugin).
 * Auth:     `Authorization: Bearer <key>` where the key lives in the
 *           `payload-mcp-api-keys` collection (created/managed in admin).
 *
 * To expose more data, edit `./collections.ts`. Globals are intentionally not
 * exposed — they hold platform secrets (SMTP, webhooks, vault references).
 */
export const mcp = mcpPlugin({
  collections: mcpCollections,
  // Re-skin the auto-generated API key collection so it lives next to other
  // platform plumbing under "System" and is named "MCP Keys".
  overrideApiKeyCollection: (collection) => ({
    ...collection,
    admin: {
      ...collection.admin,
      group: 'System',
      description:
        'Bearer tokens used to authenticate MCP clients (Claude, ChatGPT, internal agents) against the private /api/mcp endpoint. Each key controls which collections, tools and operations its holder can call.',
    },
    labels: {
      singular: 'MCP Key',
      plural: 'MCP Keys',
    },
  }),
})
