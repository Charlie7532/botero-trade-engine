/**
 * Payload MCP Gateway — delivery mechanism adapter.
 *
 * Exposes PayloadCMS collections as MCP-protocol tools so AI agents
 * (Claude, ChatGPT, internal bots) can read/write CMS data.
 *
 *  - `mcp` → private endpoint at `POST /api/mcp` (Bearer-key auth).
 *
 * The instance is configured in its own file alongside this barrel:
 * see `./private.ts`.
 */
export { mcp } from './private'
