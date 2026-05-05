'use server'

import configPromise from '@payload-config'
import { getPayload } from 'payload'
import { revalidatePath } from 'next/cache'

import { requireUser } from '@/providers/Auth/server'

export async function updatePortfolioName(portfolioId: number | string, name: string) {
  if (!name || name.trim().length === 0) {
    return { error: 'Name cannot be empty.' }
  }
  if (name.trim().length > 80) {
    return { error: 'Name must be 80 characters or fewer.' }
  }

  let user: Awaited<ReturnType<typeof requireUser>>
  try {
    user = await requireUser()
  } catch {
    return { error: 'Not authenticated.' }
  }

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

export async function updateUserProfile(
  userId: number | string,
  data: { name?: string; nickname?: string; preferredLanguage?: string },
) {
  let user: Awaited<ReturnType<typeof requireUser>>
  try {
    user = await requireUser()
  } catch {
    return { error: 'Not authenticated.' }
  }
  if (String(user.id) !== String(userId)) return { error: 'Not authorized.' }

  const name = data.name?.trim() ?? ''
  if (name.length === 0) return { error: 'Name cannot be empty.' }
  if (name.length > 80) return { error: 'Name must be 80 characters or fewer.' }

  const nickname = data.nickname?.trim() ?? ''
  if (nickname.length > 40) return { error: 'Nickname must be 40 characters or fewer.' }

  const validLanguages = ['en', 'es']
  if (data.preferredLanguage && !validLanguages.includes(data.preferredLanguage)) {
    return { error: 'Invalid language selection.' }
  }

  const payload = await getPayload({ config: configPromise })

  await payload.update({
    collection: 'users',
    id: userId,
    data: {
      name,
      nickname: nickname || undefined,
      preferredLanguage: (data.preferredLanguage as 'en' | 'es') || 'en',
    },
    overrideAccess: true,
  })

  return { success: true }
}

export async function uploadUserAvatar(userId: number | string, formData: FormData) {
  let user: Awaited<ReturnType<typeof requireUser>>
  try {
    user = await requireUser()
  } catch {
    return { error: 'Not authenticated.' }
  }
  if (String(user.id) !== String(userId)) return { error: 'Not authorized.' }

  const file = formData.get('file') as File | null
  if (!file || file.size === 0) return { error: 'No file provided.' }
  if (file.size > 5 * 1024 * 1024) return { error: 'File must be under 5 MB.' }
  if (!file.type.startsWith('image/')) return { error: 'Only image files are allowed.' }

  const payload = await getPayload({ config: configPromise })
  const buffer = Buffer.from(await file.arrayBuffer())

  const uploaded = await payload.create({
    collection: 'user-avatar',
    data: { alt: `avatar-${userId}`, user: Number(userId) },
    draft: false,
    file: {
      data: buffer,
      mimetype: file.type,
      name: file.name,
      size: file.size,
    },
    overrideAccess: true,
  })

  await payload.update({
    collection: 'users',
    id: userId,
    data: { avatar: uploaded.id },
    overrideAccess: true,
  })

  revalidatePath('/portafolio', 'layout')
  return { success: true, url: uploaded.url ?? null }
}
