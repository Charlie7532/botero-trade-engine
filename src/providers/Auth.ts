"use client"

import { useCallback } from 'react'

interface CreateUserInput {
    email: string
    password: string
    passwordConfirm: string
}

interface AuthApiError {
    message?: string
    error?: string
    errors?: Array<{ message?: string }>
}

async function parseErrorMessage(response: Response): Promise<string> {
    try {
        const data = (await response.json()) as AuthApiError
        return data.error ?? data.message ?? data.errors?.[0]?.message ?? 'Request failed'
    } catch {
        return 'Request failed'
    }
}

export function useAuth() {
    const create = useCallback(async (input: CreateUserInput) => {
        const response = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: input.email,
                password: input.password,
                passwordConfirm: input.passwordConfirm,
            }),
        })

        if (!response.ok) {
            throw new Error(await parseErrorMessage(response))
        }
    }, [])

    const logout = useCallback(async () => {
        const response = await fetch('/api/users/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        })

        if (!response.ok) {
            throw new Error(await parseErrorMessage(response))
        }
    }, [])

    return { create, logout }
}
