import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PROTECTED_PREFIXES = ['/portafolio', '/search']
const AUTH_ROUTES = new Set(['/login', '/admin/login'])
const POST_LOGIN_HOME = '/portafolio'
const TOKEN_COOKIE = 'payload-token'

function isSafeInternalPath(value: string | null | undefined): value is string {
  return !!value && value.startsWith('/') && !value.startsWith('//')
}

export function proxy(request: NextRequest) {
  const token = request.cookies.get(TOKEN_COOKIE)?.value
  const { pathname, searchParams } = request.nextUrl

  const isAuthRoute = AUTH_ROUTES.has(pathname)
  const isProtectedRoute = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + '/'),
  )

  // 1. Normalize legacy /admin/login → /login (preserve query string).
  if (pathname === '/admin/login') {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  // 2. Stale session: clear cookie, then continue to login.
  if (isAuthRoute && searchParams.get('clear') === '1') {
    const url = request.nextUrl.clone()
    url.searchParams.delete('clear')
    const response = NextResponse.redirect(url)
    response.cookies.delete(TOKEN_COOKIE)
    return response
  }

  // 3. Authenticated user on a login route → send to intended target.
  if (isAuthRoute && token) {
    const url = request.nextUrl.clone()
    const target = searchParams.get('redirect')
    url.pathname = isSafeInternalPath(target) ? target : POST_LOGIN_HOME
    url.search = ''
    return NextResponse.redirect(url)
  }

  // 4. Unauthenticated user on protected route → login.
  if (isProtectedRoute && !token) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    url.search = ''
    url.searchParams.set('redirect', pathname)
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/login',
    '/admin/login',
    '/portafolio/:path*',
    '/search/:path*',
  ],
}
