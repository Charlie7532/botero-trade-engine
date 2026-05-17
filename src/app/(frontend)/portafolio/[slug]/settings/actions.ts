'use server'

import configPromise from '@payload-config'
import { getPayload } from 'payload'
import { revalidatePath } from 'next/cache'

import { userSession } from '@/providers/Auth/server'

export async function updatePortfolioName(portfolioId: number | string, name: string) {
  if (!name || name.trim().length === 0) {
    return { error: 'Name cannot be empty.' }
  }
  if (name.trim().length > 80) {
    return { error: 'Name must be 80 characters or fewer.' }
  }

  const { user } = await userSession()
  if (!user) return { error: 'Not authenticated.' }

  const payload = await getPayload({ config: configPromise })

  // Verify the user owns or is a member of this portfolio before updating
  const existing = await payload.findByID({
    collection: 'portfolios',
    id: portfolioId,
    overrideAccess: true,
  })
  const ownerId =
    existing?.owner && typeof existing.owner === 'object'
      ? String((existing.owner as { id: number | string }).id)
      : String(existing?.owner)

  if (!existing || ownerId !== String(user.id)) {
    return { error: 'Not authorized.' }
  }

  await payload.update({
    collection: 'portfolios',
    id: portfolioId,
    data: { name: name.trim() },
    overrideAccess: true,
  })

  revalidatePath('/portafolio', 'layout')
  return { success: true }
}
