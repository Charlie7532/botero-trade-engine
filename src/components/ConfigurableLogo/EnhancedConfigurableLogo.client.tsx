'use client'
import React from 'react'
import Image from 'next/image'
import type { Media } from '@/payload-types'
import type { SiteSettings } from '@/utilities/getSiteSettings'
import { Logo } from '@/components/Logo/Logo'

interface EnhancedConfigurableLogoClientProps {
    className?: string
    priority?: boolean
    siteSettings?: SiteSettings
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    headerData?: any
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    footerData?: any
    context: 'header' | 'footer'
}

export const EnhancedConfigurableLogoClient: React.FC<EnhancedConfigurableLogoClientProps> = ({
    className = '',
    priority = false,
    siteSettings,
    headerData,
    footerData,
    context
}) => {
    // Determine which data to use based on context
    const contextData = context === 'header' ? headerData : footerData
    const logoSettings = contextData?.logo

    // Check if we should use custom logo for this context
    const useCustomLogo = logoSettings?.overrideSiteLogo

    // Get dimensions from context-specific settings or use defaults
    const height = logoSettings?.height || 40
    // Both header and footer now only control height and let width auto-adjust for proper aspect ratio

    // Cascading fallback logic for logo selection with simplified structure
    const branding = siteSettings?.branding
    const siteName = branding?.siteName || 'Main 12 LLC'
    const logoAlt = branding?.logoAlt || `${siteName} Logo`

    // Determine logo mode from context override or site settings
    let logoMode: string
    let logoLight: Media | undefined
    let logoDark: Media | undefined

    if (useCustomLogo) {
        // Use context-specific logo mode and logos
        logoMode = logoSettings?.logoMode || 'simple'

        if (logoMode === 'simple') {
            // Simple mode: use same logo for both light and dark
            const simpleLogo = logoSettings?.customLogo as Media
            logoLight = simpleLogo
            logoDark = simpleLogo
        } else {
            // Light/Dark mode: use specific logos
            logoLight = logoSettings?.customLogoLight as Media
            logoDark = logoSettings?.customLogoDark as Media
        }
    } else {
        // Use site settings logo mode and logos
        logoMode = branding?.logoMode || 'simple'

        if (logoMode === 'simple') {
            // Simple mode: use same logo for both light and dark
            const simpleLogo = branding?.logo as Media
            logoLight = simpleLogo
            logoDark = simpleLogo
        } else {
            // Light/Dark mode: use specific logos
            logoLight = branding?.logoLight as Media
            logoDark = branding?.logoDark as Media
        }
    }

    // Final fallback: if no logo is available anywhere, use the original Logo component
    if (!logoLight?.url && !logoDark?.url) {
        if (siteName && siteName !== 'Logo') {
            return (
                <span className={`font-bold text-lg ${className}`}>
                    {siteName}
                </span>
            )
        } else {
            // Use original Logo component as absolute final fallback
            return <Logo className={className} />
        }
    }

    return (
        <div className={`relative ${className}`}>
            {/* Light mode logo - shown in light mode */}
            {logoLight?.url && (
                <Image
                    src={logoLight.url}
                    alt={logoAlt}
                    width={Math.max(height * 2.5, 120)} // Ensure minimum width for optimization
                    height={height}
                    priority={priority}
                    className="object-contain dark:hidden max-w-none"
                    style={{
                        width: 'auto',
                        height: height,
                        maxHeight: height
                    }}
                    sizes={`(max-width: 768px) ${height * 2}px, ${height * 3}px`}
                    quality={95} // Higher quality for logos
                    unoptimized={false} // Ensure optimization is enabled
                />
            )}

            {/* Dark mode logo - shown in dark mode */}
            {logoDark?.url && (
                <Image
                    src={logoDark.url}
                    alt={logoAlt}
                    width={Math.max(height * 2.5, 120)} // Ensure minimum width for optimization
                    height={height}
                    priority={priority}
                    className="object-contain hidden dark:block max-w-none"
                    style={{
                        width: 'auto',
                        height: height,
                        maxHeight: height
                    }}
                    sizes={`(max-width: 768px) ${height * 2}px, ${height * 3}px`}
                    quality={95} // Higher quality for logos
                    unoptimized={false} // Ensure optimization is enabled
                />
            )}
        </div>
    )
}