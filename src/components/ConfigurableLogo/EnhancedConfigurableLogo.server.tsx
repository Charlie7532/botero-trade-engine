import React from 'react'
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

    return (
        <EnhancedConfigurableLogoClient
            siteSettings={siteSettings}
            headerData={null}
            footerData={null}
            context={context}
            className={className}
            priority={priority}
        />
    )
}