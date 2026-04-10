import React from 'react'
import { getCachedGlobal } from '@/utilities/getGlobals'
import { getCachedSiteSettings } from '@/utilities/getSiteSettings'
import { EnhancedConfigurableLogoClient } from './EnhancedConfigurableLogo.client'

interface EnhancedConfigurableLogoProps {
    className?: string
    priority?: boolean
    context: 'header' | 'footer'
}

export async function EnhancedConfigurableLogo({
    className = '',
    priority = false,
    context
}: EnhancedConfigurableLogoProps) {
    const siteSettings = await getCachedSiteSettings(1)()
    const headerData = context === 'header' ? await getCachedGlobal('header', 1)() : null
    const footerData = context === 'footer' ? await getCachedGlobal('footer', 1)() : null

    return (
        <EnhancedConfigurableLogoClient
            siteSettings={siteSettings}
            headerData={headerData}
            footerData={footerData}
            context={context}
            className={className}
            priority={priority}
        />
    )
}