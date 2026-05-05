import { headers } from 'next/headers'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { getPayload } from 'payload'

import configPromise from '@payload-config'
import type { User } from '../payload-types'

export const getMeUser = async (args?: {
  nullUserRedirect?: string
  validUserRedirect?: string
}): Promise<{
  token: string
  user: User
}> => {
  const { nullUserRedirect, validUserRedirect } = args || {}

  const cookieStore = await cookies()
  const token = cookieStore.get('payload-token')?.value

  const requestHeaders = await headers()
  const payload = await getPayload({ config: configPromise })
  const { user } = await payload.auth({ headers: requestHeaders })

  if (validUserRedirect && user) {
    redirect(validUserRedirect)
  }

  if (nullUserRedirect && !user) {
    redirect(nullUserRedirect)
  }

  // Token will exist here because if it doesn't the user will be redirected
  return {
    token: token!,
    user: user as User,
  }
}
