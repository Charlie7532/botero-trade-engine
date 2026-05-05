import type { CollectionAfterDeleteHook } from 'payload'

import { archiveAgent } from '../anthropicAgentAdapter'

/**
 * Archive the Claude Managed Agent when a bot is deleted.
 * Fails silently — deletion should not be blocked by an API error.
 */
export const archiveAgentOnDelete: CollectionAfterDeleteHook = async ({ doc, req }) => {
  const agentId = (doc as any)?.agentId
  if (!agentId || !process.env.ANTHROPIC_API_KEY) return

  try {
    await archiveAgent(agentId)
    console.log(`[AgentSync] Archived agent ${agentId} (bot deleted)`)
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Unknown error'
    req.payload.logger.error(`Failed to archive agent ${agentId}: ${msg}`)
  }
}
