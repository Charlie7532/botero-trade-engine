import type { CollectionAfterChangeHook } from 'payload'
import { getPayload } from 'payload'
import config from '@payload-config'

/**
 * After a skill is changed, find all bots that reference it and re‑save them.
 * This triggers the existing `syncAgentOnSave` hook to rebuild the system prompt.
 */
export const resyncDependentBotsOnSkillChange: CollectionAfterChangeHook = async ({
  doc,
  req,
}) => {
  const skillId = doc.id
  const payload = req.payload

  const bots = await payload.find({
    collection: 'bots',
    where: {
      skills: { contains: skillId },
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

  // Update sync metadata on the skill record
  await payload.update({
    collection: 'agent-skills',
    id: skillId,
    data: {
      lastSyncedAt: new Date().toISOString(),
      syncedBotCount: bots.totalDocs,
    },
    overrideAccess: true,
    context: { skipResync: true },
  })

  return doc
}
