'use client'

import React from 'react'
import { generateDynamicColorCSS } from '@/utilities/generateDynamicColors'

interface DynamicColorsProps {
    siteSettings: any
}

/**
 * DynamicColors component injects custom CSS color variables based on site settings.
 * Theme mode (light-only, dark-only, both) is now handled by the ThemeProvider.
 */
export const DynamicColors: React.FC<DynamicColorsProps> = ({ siteSettings }) => {
    const dynamicCSS = generateDynamicColorCSS(siteSettings)

    // Only inject styles if custom colors are enabled
    if (!dynamicCSS) {
        return null
    }

    return (
        <style
            dangerouslySetInnerHTML={{
                __html: dynamicCSS,
            }}
        />
    )
}

export default DynamicColors