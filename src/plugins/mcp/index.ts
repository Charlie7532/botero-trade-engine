/**
 * Payload MCP plugin barrel.
 *
 *  - `mcp` → private endpoint at `POST /api/mcp` (Bearer-key auth).
 *
 * The instance is configured in its own file alongside this barrel:
 * see `./private.ts`.
 */
export { mcp } from './private'
