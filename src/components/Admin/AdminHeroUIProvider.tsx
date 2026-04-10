'use client'

import React, { useEffect } from 'react'
import { useTheme } from '@payloadcms/ui'

/**
 * Syncs Payload's theme (light/dark) onto document.body so that
 * HeroUI components pick up the correct theme.
 * 
 * Note: HeroUI v3 does not require a Provider component.
 */
const AdminHeroUIThemeSync: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
    const { theme } = useTheme()

    useEffect(() => {
        // HeroUI components read theme from document attributes
        const heroTheme = theme === 'dark' ? 'dark' : 'light'
        document.body.setAttribute('data-theme', heroTheme)
        document.body.classList.toggle('dark', theme === 'dark')
        document.body.classList.toggle('light', theme !== 'dark')
    }, [theme])

    return <>{children}</>
}

export default AdminHeroUIThemeSync
