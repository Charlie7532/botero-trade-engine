import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Routes that require authentication.
 * Any route listed here will redirect unauthenticated users to /login.
 * Add new protected routes as needed.
 */
const protectedRoutes = ['/portafolio', '/search', '/admin']

/**
 * Routes that are always public (no auth required).
 * These take priority over protectedRoutes if there's overlap.
 * Add new public routes as needed.
 */
const publicRoutes: string[] = []

const adminAllowedRoles = ['superadmin', 'admin']

// Social media and search engine bots that need access to metadata
const BOT_USER_AGENTS =
  /googlebot|bingbot|slurp|duckduckbot|facebookexternalhit|facebot|twitterbot|linkedinbot|whatsapp|telegrambot|discordbot|applebot|pinterestbot/i

function isBotRequest(request: NextRequest): boolean {
  const ua = request.headers.get('user-agent') || ''
  return BOT_USER_AGENTS.test(ua)
}

function isProtectedRoute(pathname: string): boolean {
  // Public routes take priority
  if (publicRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`))) {
    return false
  }

  return protectedRoutes.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  )
}

function isAdminRoute(pathname: string): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/')
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Redirect /admin/login to /login so there's a single login page
  if (pathname === '/admin/login') {
    const loginUrl = new URL('/login', request.url)
    return NextResponse.redirect(loginUrl)
  }

  if (isProtectedRoute(pathname)) {
    // Allow bots through so they can read OpenGraph/metadata for social sharing
    if (isBotRequest(request)) {
      return NextResponse.next()
    }

    const payloadToken = request.cookies.get('payload-token')

    if (!payloadToken) {
      const loginUrl = new URL('/login', request.url)
      loginUrl.searchParams.set('redirect', pathname)
      return NextResponse.redirect(loginUrl)
    }

    // For admin routes, check if user has an allowed role
    if (isAdminRoute(pathname)) {
      try {
        // Call Payload's /api/users/me endpoint to get the full user with role
        const baseUrl = request.nextUrl.origin
        const meResponse = await fetch(`${baseUrl}/api/users/me`, {
          headers: {
            Authorization: `JWT ${payloadToken.value}`,
          },
        })

        if (!meResponse.ok) {
          // Token invalid or expired, redirect to login
          const loginUrl = new URL('/login', request.url)
          loginUrl.searchParams.set('redirect', pathname)
          return NextResponse.redirect(loginUrl)
        }

        const { user } = await meResponse.json()
        const userRole = user?.role as string | undefined

        if (!userRole || !adminAllowedRoles.includes(userRole)) {
          // Redirect unauthorized users to home page
          const homeUrl = new URL('/', request.url)
          return NextResponse.redirect(homeUrl)
        }
      } catch {
        // On error, allow request to continue (Payload will handle auth)
        return NextResponse.next()
      }
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/portafolio/:path*',
    '/search/:path*',
    '/admin/:path*',
  ],
}
