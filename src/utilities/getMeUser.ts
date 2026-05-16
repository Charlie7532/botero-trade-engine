import { headers } from 'next/headers'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { getPayload } from 'payload'

import configPromise from '@payload-config'
import type { User } from '../payload-types'

/**
 * Resolves the current user for a Server Component.
 *
 * Auth redirects are intentionally centralized here so that pages
 * never have to repeat redirect strings. The proxy (src/proxy.ts)
 * already blocks unauthenticated access to protected routes; this
 * helper handles the case the proxy cannot detect: a `payload-token`
 * cookie that is present but no longer valid (stale session,
 * cross-subdomain mismatch, revoked user, etc.). In that case we
 * redirect to `/login?clear=1&redirect=…`, which signals the proxy
 * to delete the stale cookie before showing the login form — this
 * is what breaks the redirect loop.
 */
export const getMeUser = async (args?: {
  validUserRedirect?: string
}): Promise<{
  token: string
  user: User
}> => {
  const { validUserRedirect } = args || {}

  const cookieStore = await cookies()
  const token = cookieStore.get('payload-token')?.value

  const requestHeaders = await headers()
  const payload = await getPayload({ config: configPromise })
  const { user } = await payload.auth({ headers: requestHeaders })

  if (validUserRedirect && user) {
    redirect(validUserRedirect)
  }

  if (!user) {
    // Token may exist but be invalid — the `clear=1` flag tells the
    // proxy to delete the stale cookie. Without a token at all this
    // is also the right destination (the proxy would have done the
    // same thing for a protected route).
    redirect('/login?clear=1&redirect=%2Fportafolio')
  }

  return {
    token: token!,
    user: user as User,
  }
}
