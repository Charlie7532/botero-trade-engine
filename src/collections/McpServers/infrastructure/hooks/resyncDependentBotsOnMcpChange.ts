import type { CollectionAfterChangeHook } from 'payload'

/**
 * After an MCP server is changed, find all bots that reference it and trigger
 * a re‑save so that the bot's system prompt is rebuilt with the new MCP config.
 */
export const resyncDependentBotsOnMcpChange: CollectionAfterChangeHook = async ({
  doc,
  req,
}) => {
  const mcpId = doc.id
  const payload = req.payload

  const bots = await payload.find({
    collection: 'bots',
    where: {
      mcpServers: { contains: mcpId },
    },
    limit: 0,
    overrideAccess: true,
  })

  for (const bot of bots.docs) {
    await payload.update({
      collection: 'bots',
      id: bot.id,
      data: {},
      overrideAccess: true,
    })
  }

  // Record sync metadata on the MCP for admin visibility
  await payload.update({
    collection: 'mcp-servers',
    id: mcpId,
    data: {
      lastSyncedAt: new Date().toISOString(),
      syncedBotCount: bots.totalDocs,
    },
    overrideAccess: true,
    context: { skipResync: true },
  })

  return doc
}
