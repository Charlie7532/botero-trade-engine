'use client'

import React from 'react'
import Link from 'next/link'
import { EnhancedConfigurableLogoClient } from '@/components/ConfigurableLogo/EnhancedConfigurableLogo.client'
import { HeaderNav } from '../Nav'
import { HamburgerButton } from '../HamburgerButton'

import type { Header } from '@/payload-types'
import type { SiteSettings } from '@/utilities/getSiteSettings'

interface MinimalHeaderProps {
    data: Header
    siteSettings?: SiteSettings
    isMobileMenuOpen: boolean
    toggleMobileMenu: () => void
}

export const MinimalHeader: React.FC<MinimalHeaderProps> = ({
    data,
    siteSettings,
    isMobileMenuOpen,
    toggleMobileMenu
}) => {
    return (
        <div className="py-8 flex items-center justify-between">
            <Link href="/">
                <EnhancedConfigurableLogoClient
                    siteSettings={siteSettings}
                    headerData={data}
                    context="header"
                    className=""
                    priority={true}
                />
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex flex-1">
                <HeaderNav data={data} />
            </div>

            {/* Mobile Hamburger Button - Always on the right */}
            <HamburgerButton
                isOpen={isMobileMenuOpen}
                onClick={toggleMobileMenu}
            />
        </div>
    )
}