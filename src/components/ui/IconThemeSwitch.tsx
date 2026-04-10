'use client'

import React from 'react'
import { useTheme } from '@/providers/Theme'

const SunIcon = () => (
    <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
    >
        <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
        />
    </svg>
)

const MoonIcon = () => (
    <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
    >
        <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
        />
    </svg>
)

export const IconThemeSwitch: React.FC = () => {
    const { theme, setTheme, resolvedTheme } = useTheme()
    const [mounted, setMounted] = React.useState(false)

    // Avoid hydration mismatch
    React.useEffect(() => {
        setMounted(true)
    }, [])

    const toggleTheme = () => {
        setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
    }

    // Show placeholder during SSR to avoid hydration mismatch
    if (!mounted) {
        return (
            <button
                className="group w-9 h-9 rounded-full border border-gray-300 flex justify-center items-center dark:border-gray-600"
                aria-label="Toggle theme"
                data-theme-switch
                disabled
            >
                <div className="w-5 h-5" />
            </button>
        )
    }

    const isDark = resolvedTheme === 'dark'

    return (
        <button
            onClick={toggleTheme}
            className="group w-9 h-9 rounded-full border border-gray-300 flex justify-center items-center transition-all duration-500 hover:text-secondary-500 hover:border-secondary-500 dark:border-gray-600 dark:hover:border-secondary-400"
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}
            data-theme-switch
        >
            <div className="text-gray-700 transition-all duration-500 group-hover:text-secondary-500 dark:text-gray-300 dark:group-hover:text-secondary-400">
                {isDark ? <SunIcon /> : <MoonIcon />}
            </div>
        </button>
    )
}