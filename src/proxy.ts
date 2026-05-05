import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === '/admin/login') {
    const url = new URL('/login', request.url)
    const existingRedirect = request.nextUrl.searchParams.get('redirect')
    url.searchParams.set('redirect', existingRedirect ?? '/portafolio')
    return NextResponse.redirect(url)
  }

  const token = request.cookies.get('payload-token')?.value

  if (request.nextUrl.pathname === '/' && token) {
    return NextResponse.redirect(new URL('/portafolio', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/', '/admin/login'],
}
