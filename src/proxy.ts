import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  const token = request.cookies.get('payload-token')?.value
  const pathname = request.nextUrl.pathname

  // Protected routes that require authentication
  const protectedRoutes = [
    '/portafolio',
    '/search',
  ]
  const isProtectedRoute = protectedRoutes.some(route => pathname === route || pathname.startsWith(route + '/'))

  // If accessing protected route without token → redirect to login
  if (isProtectedRoute && !token) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('redirect', pathname)
    return NextResponse.redirect(loginUrl)
  }

  // If accessing root with token → redirect to portafolio
  if (pathname === '/' && token) {
    return NextResponse.redirect(new URL('/portafolio', request.url))
  }

  // Legacy admin login route redirect
  if (pathname === '/admin/login') {
    const url = new URL('/login', request.url)
    const existingRedirect = request.nextUrl.searchParams.get('redirect')
    url.searchParams.set('redirect', existingRedirect ?? '/portafolio')
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/', '/login', '/admin/login', '/portafolio/:path*', '/search/:path*'],
}
