'use server'

import configPromise from '@payload-config'
import { getPayload } from 'payload'
import type { RequiredDataFromCollectionSlug } from 'payload'
import { revalidatePath } from 'next/cache'

import { userSession } from '@/providers/Auth/server'

export type CreatePortfolioInput = {
  name: string
}

export type CreatePortfolioResult =
  | { ok: true; id: string | number; slug: string }
  | { ok: false; error: string }

export async function createPortfolio(
  input: CreatePortfolioInput,
): Promise<CreatePortfolioResult> {
  const { user } = await userSession()
  if (!user) return { ok: false, error: 'Not authenticated.' }

  const name = input.name?.trim()
  if (!name) return { ok: false, error: 'Name is required.' }
  if (name.length > 80) return { ok: false, error: 'Name must be 80 characters or fewer.' }

  const payload = await getPayload({ config: configPromise })

  try {
    const created = await payload.create({
      collection: 'portfolios',
      data: {
        name,
        status: 'active',
      } as unknown as RequiredDataFromCollectionSlug<'portfolios'>,
      user,
      overrideAccess: false,
    })
    revalidatePath('/portafolio')
    return { ok: true, id: created.id, slug: String(created.slug) }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create portfolio.'
    return { ok: false, error: message }
  }
}
