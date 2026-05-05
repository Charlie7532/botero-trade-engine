'use client'

import type { User } from '@/payload-types'

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState, useRef } from 'react'

// Cache key for storing user data
const USER_CACHE_KEY = 'auth_user_cache'
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes in milliseconds

interface CachedUser {
  user: User | null
  timestamp: number
}

// Get cached user from sessionStorage
const getCachedUser = (): User | null => {
  if (typeof window === 'undefined') return null
  try {
    const cached = sessionStorage.getItem(USER_CACHE_KEY)
    if (!cached) return null
    const { user, timestamp }: CachedUser = JSON.parse(cached)
    // Check if cache is still valid
    if (Date.now() - timestamp > CACHE_TTL) {
      sessionStorage.removeItem(USER_CACHE_KEY)
      return null
    }
    return user
  } catch {
    return null
  }
}

// Set user in cache
const setCachedUser = (user: User | null): void => {
  if (typeof window === 'undefined') return
  try {
    const cached: CachedUser = { user, timestamp: Date.now() }
    sessionStorage.setItem(USER_CACHE_KEY, JSON.stringify(cached))
  } catch {
    // Ignore storage errors
  }
}

// Clear user cache
const clearUserCache = (): void => {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.removeItem(USER_CACHE_KEY)
  } catch {
    // Ignore storage errors
  }
}


type ResetPassword = (args: {
  password: string
  passwordConfirm: string
  token: string
}) => Promise<void>

type ForgotPassword = (args: { email: string }) => Promise<void>

type Create = (args: { email: string; password: string; passwordConfirm: string }) => Promise<void>

type Login = (args: { email: string; password: string }) => Promise<User>

type Logout = () => Promise<void>

type AuthContext = {
  create: Create
  forgotPassword: ForgotPassword
  isLoading: boolean
  login: Login
  logout: Logout
  resetPassword: ResetPassword
  setUser: (user: User | null) => void
  status: 'loggedIn' | 'loggedOut' | undefined
  user?: User | null
}

const Context = createContext({} as AuthContext)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Initialize with cached user for instant loading
  const [user, setUser] = useState<User | null | undefined>(() => getCachedUser())
  const [isLoading, setIsLoading] = useState(() => !getCachedUser())
  const hasFetched = useRef(false)

  // used to track the single event of logging in or logging out
  // useful for `useEffect` hooks that should only run once
  const [status, setStatus] = useState<'loggedIn' | 'loggedOut' | undefined>()
  const create = useCallback<Create>(async (args) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/create`, {
        body: JSON.stringify({
          email: args.email,
          password: args.password,
          passwordConfirm: args.passwordConfirm,
        }),
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        method: 'POST',
      })

      if (res.ok) {
        const { errors } = await res.json()
        if (errors) throw new Error(errors[0].message)

        // Authenticate on the client after successful account creation.
        const loginRes = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/login`, {
          body: JSON.stringify({
            email: args.email,
            password: args.password,
          }),
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          method: 'POST',
        })

        if (!loginRes.ok) {
          throw new Error('Account created, but sign-in failed. Please sign in manually.')
        }

        const { errors: loginErrors, user: loggedInUser } = await loginRes.json()
        if (loginErrors) throw new Error(loginErrors[0].message)

        setUser(loggedInUser)
        setCachedUser(loggedInUser)
        setStatus('loggedIn')
      } else {
        const errorPayload = await res.json().catch(() => null)
        const message = errorPayload?.errors?.[0]?.message || 'Unable to create account.'
        throw new Error(message)
      }
    } catch (e: any) {
      throw new Error(e?.message || 'An error occurred while creating your account.')
    }
  }, [])

  const login = useCallback<Login>(async (args) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/login`, {
        body: JSON.stringify({
          email: args.email,
          password: args.password,
        }),
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        method: 'POST',
      })

      if (res.ok) {
        const { errors, user } = await res.json()
        if (errors) throw new Error(errors[0].message)
        setUser(user)
        setCachedUser(user)
        setStatus('loggedIn')

        return user
      }

      throw new Error('Invalid login')
    } catch (e) {
      throw new Error('An error occurred while attempting to login.')
    }
  }, [])

  const logout = useCallback<Logout>(async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/logout`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        method: 'POST',
      })

      if (res.ok) {
        setUser(null)
        clearUserCache()
        setStatus('loggedOut')
      } else {
        throw new Error('An error occurred while attempting to logout.')
      }
    } catch (e) {
      throw new Error('An error occurred while attempting to logout.')
    }
  }, [])

  useEffect(() => {
    const fetchMe = async () => {
      // Skip if already fetched in this session
      if (hasFetched.current) return
      hasFetched.current = true

      // If we have cached user, still fetch in background but don't show loading
      const cachedUser = getCachedUser()
      if (!cachedUser) {
        setIsLoading(true)
      }

      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/me`, {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          method: 'GET',
        })

        if (res.ok) {
          const { user: meUser } = await res.json()
          setUser(meUser || null)
          setCachedUser(meUser || null)
          setStatus(meUser ? 'loggedIn' : undefined)
        } else {
          setUser(null)
          clearUserCache()
        }
      } catch (e) {
        setUser(null)
        clearUserCache()
      } finally {
        setIsLoading(false)
      }
    }

    void fetchMe()
  }, [])

  const forgotPassword = useCallback<ForgotPassword>(async (args) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/forgot-password`, {
        body: JSON.stringify({
          email: args.email,
        }),
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        method: 'POST',
      })

      if (res.ok) {
        const { data, errors } = await res.json()
        if (errors) throw new Error(errors[0].message)
        setUser(data?.loginUser?.user)
      } else {
        throw new Error('Invalid login')
      }
    } catch (e) {
      throw new Error('An error occurred while attempting to login.')
    }
  }, [])

  const resetPassword = useCallback<ResetPassword>(async (args) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_SERVER_URL}/api/users/reset-password`, {
        body: JSON.stringify({
          password: args.password,
          passwordConfirm: args.passwordConfirm,
          token: args.token,
        }),
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        method: 'POST',
      })

      if (res.ok) {
        const { data, errors } = await res.json()
        if (errors) throw new Error(errors[0].message)
        setUser(data?.loginUser?.user)
        setStatus(data?.loginUser?.user ? 'loggedIn' : undefined)
      } else {
        throw new Error('Invalid login')
      }
    } catch (e) {
      throw new Error('An error occurred while attempting to login.')
    }
  }, [])

  return (
    <Context.Provider
      value={{
        create,
        forgotPassword,
        isLoading,
        login,
        logout,
        resetPassword,
        setUser,
        status,
        user,
      }}
    >
      {children}
    </Context.Provider>
  )
}

type UseAuth<T = User> = () => AuthContext

export const useAuth: UseAuth = () => useContext(Context)

/**
 * Convenience hook to get the current user and loading state
 * Adds isAdmin computed property to the user object for easy admin checks
 */
export const useUser = () => {
  const { user, isLoading, status } = useContext(Context)

  // Compute isAdmin based on user role
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  // Memoize the user object to prevent creating a new reference on every render.
  // Without this, every consumer that uses `user` in a dependency array
  // (e.g. useCallback, useEffect) would re-run on every render, causing infinite loops.
  const userWithRoles = useMemo(
    () => (user ? { ...user, isAdmin } : null),
    [user, isAdmin],
  )

  return useMemo(
    () => ({ user: userWithRoles, isLoading, status }),
    [userWithRoles, isLoading, status],
  )
}
