'use client'

import React from 'react'
import Link from 'next/link'
import { EnhancedConfigurableLogoClient } from '@/components/ConfigurableLogo/EnhancedConfigurableLogo.client'
import { HeaderNav } from '../Nav'
import { HamburgerButton } from '../HamburgerButton'
import { IconThemeSwitch } from '@/components/ui/IconThemeSwitch'

import type { Header } from '@/payload-types'
import type { SiteSettings } from '@/utilities/getSiteSettings'

interface ModernHeaderProps {
    data: Header
    siteSettings?: SiteSettings
    isMobileMenuOpen: boolean
    toggleMobileMenu: () => void
}

export const ModernHeader: React.FC<ModernHeaderProps> = ({
    data,
    siteSettings,
    isMobileMenuOpen,
    toggleMobileMenu
}) => {
    return (
        <div className="py-8 flex items-center relative">
            {/* Logo */}
            <Link href="/" className="flex items-center">
                <EnhancedConfigurableLogoClient
                    siteSettings={siteSettings}
                    headerData={data}
                    context="header"
                    className="h-8"
                    priority={true}
                />
            </Link>

            {/* Desktop Navigation - Flexible positioning */}
            <div className="hidden md:flex flex-1">
                <HeaderNav data={data} />
            </div>

            {/* Right Side Actions */}
            <div className="flex items-center space-x-4">
                {/* Theme Switch - Desktop Only */}
                <div className="hidden md:block">
                    <IconThemeSwitch />
                </div>

                {/* Mobile Hamburger Button - Always on the right */}
                <HamburgerButton
                    isOpen={isMobileMenuOpen}
                    onClick={toggleMobileMenu}
                />
            </div>
        </div>
    )
}