import type { CollectionAfterChangeHook } from 'payload'

import {
  createAgent,
  updateAgent,
} from '../anthropicAgentAdapter'

/**
 * After a Bot is saved, sync its config to a Claude Managed Agent.
 * - Skips if context.skipAgentSync is set (prevents infinite loops).
 * - New bots (no agentId): creates an agent, patches agentId + version back.
 * - Existing bots (has agentId): updates the agent, patches new version back.
 * - On error: sets syncStatus to 'error' with the message.
 */
export const syncAgentOnSave: CollectionAfterChangeHook = async ({ doc, req, context }) => {
  // Prevent infinite loops — this hook patches the doc, which triggers afterChange again
  if (context?.skipAgentSync) return doc

  // Skip if no API key configured
  if (!process.env.ANTHROPIC_API_KEY) return doc

  // Only sync AI agent bots, not traditional strategies
  if (doc.executionType !== 'agent') return doc

  // Resolve MCP server relationships
  const mcpServerIds = doc.mcpServers ?? []
  const mcpConfigs: Array<{ name: string; type: 'url'; url: string }> = []

  if (mcpServerIds.length > 0) {
    const resolved = await req.payload.find({
      collection: 'mcp-servers',
      where: {
        id: { in: mcpServerIds.map((s: any) => (typeof s === 'object' ? s.id : s)) },
        isActive: { equals: true },
        type: { equals: 'url' },
      },
      limit: 50,
      depth: 0,
      overrideAccess: true,
    })

    for (const mcp of resolved.docs) {
      const mcpDoc = mcp as any
      if (mcpDoc.url && mcpDoc.slug) {
        mcpConfigs.push({ name: mcpDoc.slug, type: 'url', url: mcpDoc.url })
      }
    }
  }

  // Resolve built-in Anthropic skills
  const skillIds = doc.skills ?? []
  const builtinSkills: Array<{ name: string }> = []

  if (skillIds.length > 0) {
    const resolvedSkills = await req.payload.find({
      collection: 'agent-skills',
      where: {
        id: { in: skillIds.map((s: any) => (typeof s === 'object' ? s.id : s)) },
        isActive: { equals: true },
        type: { equals: 'builtin' },
      },
      limit: 50,
      depth: 0,
      overrideAccess: true,
    })

    for (const skill of resolvedSkills.docs) {
      const skillDoc = skill as any
      if (skillDoc.builtinId) {
        builtinSkills.push({ name: skillDoc.builtinId })
      }
    }
  }

  // Build custom skill prompt additions
  const customSkillPrompts: string[] = []
  if (skillIds.length > 0) {
    const resolvedCustom = await req.payload.find({
      collection: 'agent-skills',
      where: {
        id: { in: skillIds.map((s: any) => (typeof s === 'object' ? s.id : s)) },
        isActive: { equals: true },
        type: { equals: 'custom' },
      },
      limit: 50,
      depth: 0,
      overrideAccess: true,
    })

    for (const skill of resolvedCustom.docs) {
      const skillDoc = skill as any
      if (skillDoc.promptContent) {
        customSkillPrompts.push(`## Skill: ${skillDoc.name}\n${skillDoc.promptContent}`)
      }
    }
  }

  // Build full system prompt (base + custom skills appended)
  let systemPrompt = doc.systemPrompt || ''
  if (customSkillPrompts.length > 0) {
    systemPrompt += '\n\n---\n\n# Active Skills\n\n' + customSkillPrompts.join('\n\n')
  }

  const agentConfig = {
    name: doc.name,
    model: doc.model || 'claude-sonnet-4-6',
    system: systemPrompt || undefined,
    description: doc.description || undefined,
    mcp_servers: mcpConfigs.length > 0 ? mcpConfigs : undefined,
    skills: builtinSkills.length > 0 ? builtinSkills : undefined,
    metadata: {
      botero_bot_id: String(doc.id),
      strategy_type: doc.strategyType || '',
      ...(doc.agentMetadata || {}),
    },
  }

  try {
    let result: { id: string; version: number }

    if (!doc.agentId) {
      result = await createAgent(agentConfig)
      console.log(`[AgentSync] Created agent ${result.id} for bot ${doc.id}`)
    } else {
      result = await updateAgent(doc.agentId, doc.agentVersion || 1, agentConfig)
      console.log(`[AgentSync] Updated agent ${result.id} v${result.version}`)
    }

    // Patch the agent identity back onto the document
    await req.payload.update({
      collection: 'bots',
      id: doc.id,
      data: {
        agentId: result.id,
        agentVersion: result.version,
        agentSyncStatus: 'synced',
        agentSyncError: '',
      },
      overrideAccess: true,
      context: { skipAgentSync: true },
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown sync error'
    console.error(`[AgentSync] FAILED for bot ${doc.id}:`, message)
    req.payload.logger.error(`Agent sync failed for bot ${doc.id}: ${message}`)

    await req.payload.update({
      collection: 'bots',
      id: doc.id,
      data: {
        agentSyncStatus: 'error',
        agentSyncError: message.slice(0, 500),
      },
      overrideAccess: true,
      context: { skipAgentSync: true },
    })
  }

  return doc
}
