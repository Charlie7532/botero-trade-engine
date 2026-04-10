'use client'

import { useEffect } from 'react'
import { generateDynamicCSS, getThemeConfig } from '@/utilities/dynamicStyles'

interface DynamicStylesProps {
    siteSettings: any
}

export function DynamicStyles({ siteSettings }: DynamicStylesProps) {
    useEffect(() => {
        // Remove existing dynamic styles
        const existingStyle = document.getElementById('dynamic-site-styles')
        if (existingStyle) {
            existingStyle.remove()
        }

        // Generate and inject new styles
        const css = generateDynamicCSS(siteSettings)
        if (css) {
            const styleElement = document.createElement('style')
            styleElement.id = 'dynamic-site-styles'
            styleElement.textContent = css
            document.head.appendChild(styleElement)
        }

        // Handle theme mode restrictions
        const themeConfig = getThemeConfig(siteSettings)

        // Set the initial theme based on settings
        if (!themeConfig.supportsBoth) {
            // Force a specific theme if only one is supported
            const forcedTheme = themeConfig.themeMode === 'light-only' ? 'light' : 'dark'
            document.documentElement.setAttribute('data-theme', forcedTheme)

            // Hide theme switcher if only one theme is supported
            const themeSwitchers = document.querySelectorAll('[data-theme-switch]')
            themeSwitchers.forEach(switcher => {
                (switcher as HTMLElement).style.display = 'none'
            })
        } else {
            // Show theme switcher if both themes are supported
            const themeSwitchers = document.querySelectorAll('[data-theme-switch]')
            themeSwitchers.forEach(switcher => {
                (switcher as HTMLElement).style.display = ''
            })

            // Set default theme if specified and not already set
            const currentTheme = document.documentElement.getAttribute('data-theme')
            if (!currentTheme && themeConfig.defaultTheme !== 'system') {
                document.documentElement.setAttribute('data-theme', themeConfig.defaultTheme)
            }
        }

    }, [siteSettings])

    return null // This component doesn't render anything
}

export default DynamicStyles