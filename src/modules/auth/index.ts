"use client"

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

type LoginStep = 'email' | 'password' | 'otp-prompt'

interface AuthErrorResponse {
    error?: string
    message?: string
}

interface CheckEmailResponse {
    exists: boolean
    hasPassword: boolean
}

interface ApiSuccessResponse {
    success: boolean
    message?: string
    error?: string
}

interface UseLoginFlowOptions {
    redirectTo: string
}

interface VerifyOtpOptions {
    email: string
    purpose: string
    redirectTo: string
}

interface UseSetPasswordFlowOptions {
    redirectTo: string
}

interface PasswordStrengthState {
    hasMinLength: boolean
    hasUppercase: boolean
    hasNumber: boolean
    hasSpecialChar: boolean
}

interface StrengthDisplay {
    label: string
    color: string
    width: string
}

const DEFAULT_ERROR_MESSAGE = 'Something went wrong. Please try again.'

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
    try {
        const data = (await response.json()) as AuthErrorResponse
        return data.error ?? data.message ?? fallback
    } catch {
        return fallback
    }
}

function getQueryRedirect(basePath: string, redirectTo: string): string {
    const params = new URLSearchParams({ redirect: redirectTo })
    return `${basePath}?${params.toString()}`
}

export function useLoginFlow({ redirectTo }: UseLoginFlowOptions) {
    const router = useRouter()
    const [step, setStep] = useState<LoginStep>('email')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [isSendingOtp, setIsSendingOtp] = useState(false)
    const [showPassword, setShowPassword] = useState(false)

    const handleEmailSubmit = useCallback(async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setError(null)
        setIsLoading(true)

        try {
            const response = await fetch('/api/auth/check-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            })

            if (!response.ok) {
                throw new Error(await getErrorMessage(response, DEFAULT_ERROR_MESSAGE))
            }

            const data = (await response.json()) as CheckEmailResponse

            if (!data.exists) {
                setError('No account found with that email address.')
                return
            }

            setStep(data.hasPassword ? 'password' : 'otp-prompt')
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsLoading(false)
        }
    }, [email])

    const handlePasswordSubmit = useCallback(async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setError(null)
        setIsLoading(true)

        try {
            const response = await fetch('/api/users/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            })

            if (!response.ok) {
                throw new Error(await getErrorMessage(response, DEFAULT_ERROR_MESSAGE))
            }

            router.push(redirectTo)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsLoading(false)
        }
    }, [email, password, redirectTo, router])

    const handleSendOtp = useCallback(async () => {
        setError(null)
        setIsSendingOtp(true)

        try {
            const response = await fetch('/api/auth/otp/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, purpose: 'login' }),
            })

            if (!response.ok) {
                throw new Error(await getErrorMessage(response, DEFAULT_ERROR_MESSAGE))
            }

            const params = new URLSearchParams({
                email,
                purpose: 'login',
                redirect: redirectTo,
            })
            router.push(`/verify-otp?${params.toString()}`)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsSendingOtp(false)
        }
    }, [email, redirectTo, router])

    const handleEditEmail = useCallback(() => {
        setStep('email')
        setPassword('')
        setError(null)
    }, [])

    const handleGoogleLogin = useCallback(() => {
        const state = encodeURIComponent(redirectTo || '/account')
        window.location.assign(`/api/users/oauth/google?state=${state}`)
    }, [redirectTo])

    return {
        step,
        email,
        password,
        error,
        isLoading,
        isSendingOtp,
        showPassword,
        setEmail,
        setPassword,
        setShowPassword,
        handleEmailSubmit,
        handlePasswordSubmit,
        handleSendOtp,
        handleEditEmail,
        handleGoogleLogin,
    }
}

export function useForgotPasswordFlow() {
    const router = useRouter()
    const [email, setEmail] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(false)

    const handleSubmit = useCallback(async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setError(null)
        setIsLoading(true)

        try {
            const response = await fetch('/api/auth/otp/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, purpose: 'password-reset' }),
            })

            if (!response.ok) {
                throw new Error(await getErrorMessage(response, DEFAULT_ERROR_MESSAGE))
            }

            const params = new URLSearchParams({
                email,
                purpose: 'password-reset',
                redirect: '/account',
            })
            router.push(`/verify-otp?${params.toString()}`)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsLoading(false)
        }
    }, [email, router])

    return {
        email,
        error,
        isLoading,
        setEmail,
        handleSubmit,
    }
}

export function useVerifyOtpFlow({ email, purpose, redirectTo }: VerifyOtpOptions) {
    const router = useRouter()
    const [otp, setOtp] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [isResending, setIsResending] = useState(false)
    const [resendCooldown, setResendCooldown] = useState(0)

    useEffect(() => {
        if (resendCooldown <= 0) {
            return
        }

        const timer = window.setInterval(() => {
            setResendCooldown((previous) => Math.max(previous - 1, 0))
        }, 1000)

        return () => window.clearInterval(timer)
    }, [resendCooldown])

    const handleSubmit = useCallback(async (submittedOtp: string) => {
        setError(null)
        setIsLoading(true)

        try {
            const response = await fetch('/api/auth/otp/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, otp: submittedOtp }),
            })

            if (!response.ok) {
                throw new Error(await getErrorMessage(response, DEFAULT_ERROR_MESSAGE))
            }

            if (purpose === 'password-reset') {
                router.push(getQueryRedirect('/set-password', redirectTo))
                return
            }

            router.push(redirectTo)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsLoading(false)
        }
    }, [email, purpose, redirectTo, router])

    const handleComplete = useCallback((value: string) => {
        if (value.length === 6) {
            void handleSubmit(value)
        }
    }, [handleSubmit])

    const handleResendCode = useCallback(async () => {
        setError(null)
        setIsResending(true)

        try {
            const response = await fetch('/api/auth/otp/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, purpose }),
            })

            const data = (await response.json()) as ApiSuccessResponse

            if (!response.ok || !data.success) {
                throw new Error(data.error ?? DEFAULT_ERROR_MESSAGE)
            }

            setResendCooldown(60)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsResending(false)
        }
    }, [email, purpose])

    return {
        otp,
        error,
        isLoading,
        isResending,
        resendCooldown,
        setOtp,
        handleSubmit,
        handleComplete,
        handleResendCode,
    }
}

function evaluateStrength(password: string): PasswordStrengthState {
    return {
        hasMinLength: password.length >= 8,
        hasUppercase: /[A-Z]/.test(password),
        hasNumber: /\d/.test(password),
        hasSpecialChar: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    }
}

function getStrengthDisplayFromState(strength: PasswordStrengthState): StrengthDisplay {
    const score = Object.values(strength).filter(Boolean).length

    if (score <= 1) {
        return {
            label: 'Weak',
            color: 'bg-red-500',
            width: '33%',
        }
    }

    if (score <= 3) {
        return {
            label: 'Medium',
            color: 'bg-yellow-500',
            width: '66%',
        }
    }

    return {
        label: 'Strong',
        color: 'bg-green-500',
        width: '100%',
    }
}

export function useSetPasswordFlow({ redirectTo }: UseSetPasswordFlowOptions) {
    const router = useRouter()
    const [password, setPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [showPassword, setShowPassword] = useState(false)
    const [showConfirmPassword, setShowConfirmPassword] = useState(false)

    const strength = useMemo(() => evaluateStrength(password), [password])
    const passwordsMatch = password === confirmPassword

    const getStrengthDisplay = useCallback(() => {
        return getStrengthDisplayFromState(strength)
    }, [strength])

    const handleSubmit = useCallback(async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setError(null)

        if (!passwordsMatch) {
            setError('Passwords do not match.')
            return
        }

        setIsLoading(true)

        try {
            const response = await fetch('/api/auth/set-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password, confirmPassword }),
            })

            const data = (await response.json()) as ApiSuccessResponse

            if (!response.ok || !data.success) {
                throw new Error(data.error ?? DEFAULT_ERROR_MESSAGE)
            }

            router.push(redirectTo)
        } catch (err) {
            setError(err instanceof Error ? err.message : DEFAULT_ERROR_MESSAGE)
        } finally {
            setIsLoading(false)
        }
    }, [confirmPassword, password, passwordsMatch, redirectTo, router])

    const handleSkip = useCallback(() => {
        router.push(redirectTo)
    }, [redirectTo, router])

    return {
        password,
        confirmPassword,
        error,
        isLoading,
        showPassword,
        showConfirmPassword,
        strength,
        passwordsMatch,
        getStrengthDisplay,
        setPassword,
        setConfirmPassword,
        setShowPassword,
        setShowConfirmPassword,
        handleSubmit,
        handleSkip,
    }
}
