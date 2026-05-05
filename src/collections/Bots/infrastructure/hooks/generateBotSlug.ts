import crypto from 'crypto'
import type { CollectionBeforeChangeHook } from 'payload'

/**
 * Auto-generate a 12-char hex slug for bots that don't have one.
 * Runs on both create and update so existing bots get a slug when re-saved.
 */
export const generateBotSlug: CollectionBeforeChangeHook = ({ data }) => {
  if (!data.botSlug) {
    data.botSlug = crypto.randomBytes(6).toString('hex')
  }
  return data
}
