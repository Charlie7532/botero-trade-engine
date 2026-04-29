import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  const token = request.cookies.get('payload-token')?.value

  if (request.nextUrl.pathname === '/' && token) {
    return NextResponse.redirect(new URL('/portafolio', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/'],
}
