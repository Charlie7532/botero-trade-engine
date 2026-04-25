'use client'
import { useHeaderTheme } from '@/providers/HeaderTheme'
import { usePathname } from 'next/navigation'
import React, { useEffect, useState } from 'react'

import type { Header } from '@/payload-types'
import type { SiteSettings } from '@/utilities/getSiteSettings'

// import { EnhancedConfigurableLogoClient } from '@/components/ConfigurableLogo/EnhancedConfigurableLogo.client'
// import { HeaderNav } from './Nav'
import { MobileMenuDrawer } from './MobileMenuDrawer'
import { DefaultHeader } from './styles/DefaultHeader'
import { ModernHeader } from './styles/ModernHeader'
import { MinimalHeader } from './styles/MinimalHeader'

interface HeaderClientProps {
  data: Header
  siteSettings?: SiteSettings
}

export const HeaderClient: React.FC<HeaderClientProps> = ({ data, siteSettings }) => {
  /* Storing the value in a useState to avoid hydration errors */
  const [theme, setTheme] = useState<string | null>(null)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const { headerTheme, setHeaderTheme } = useHeaderTheme()
  const pathname = usePathname()

  const navItems = data?.navItems || []
  const headerStyle = data?.headerStyle || 'default'

  useEffect(() => {
    setHeaderTheme(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname])

  useEffect(() => {
    if (headerTheme && headerTheme !== theme) setTheme(headerTheme)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headerTheme])

  // Close mobile menu when pathname changes
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [pathname])

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen)
  }

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false)
  }

  // Get header styles for background, positioning, and text color
  const getHeaderStyles = () => {
    // @ts-expect-error settings were flattened in schema
    const backgroundType = data?.backgroundType || data?.settings?.backgroundType || 'transparent'
    // @ts-expect-error settings were flattened in schema
    const backgroundColor = data?.backgroundColor || data?.settings?.backgroundColor || '#ffffff'
    // @ts-expect-error settings were flattened in schema
    const textColor = data?.textColor || data?.settings?.textColor || 'auto'
    // @ts-expect-error settings were flattened in schema
    const isSticky = data?.sticky || data?.settings?.sticky || false

    let backgroundClasses = ''
    let textClasses = ''
    let stickyClasses = ''
    const style: React.CSSProperties = {}

    // Background styles
    switch (backgroundType) {
      case 'transparent':
        backgroundClasses = 'bg-transparent'
        break
      case 'semi-transparent':
        backgroundClasses = 'backdrop-blur-md'
        style.backgroundColor = backgroundColor ? `${backgroundColor}90` : '#ffffff50'
        break
      case 'solid':
        style.backgroundColor = backgroundColor || '#ffffff'
        break
    }

    // Text color styles
    switch (textColor) {
      case 'primary':
        textClasses = 'text-primary'
        break
      case 'custom':
        // @ts-expect-error settings were flattened in schema
        const customColor = data?.customTextColor || data?.settings?.customTextColor
        if (customColor) {
          // Use inline style approach which is more reliable for dynamic colors
          style.color = customColor
          textClasses = ''
        } else {
          textClasses = 'text-gray-900 dark:text-white'
        }
        break
      case 'auto':
      default:
        // Auto should be black in light theme, white in dark theme
        textClasses = 'text-gray-900 dark:text-white'
        break
    }

    // Sticky positioning - safe for admin bar
    if (isSticky) {
      stickyClasses = 'header-sticky border-b border-gray-200/20 dark:border-gray-700/20'
    }

    // Set high z-index for header
    style.zIndex = 99999

    return {
      className: `w-full header-with-admin-bar ${backgroundClasses} ${textClasses} ${stickyClasses}`,
      style
    }
  }

  // Render the appropriate header style
  const renderHeaderStyle = () => {
    const commonProps = {
      data,
      siteSettings,
      theme,
      isMobileMenuOpen,
      toggleMobileMenu
    }

    switch (headerStyle) {
      case 'modern':
        return <ModernHeader {...commonProps} />
      case 'minimal':
        return <MinimalHeader {...commonProps} />
      case 'default':
      default:
        return <DefaultHeader {...commonProps} />
    }
  }

  const headerStyles = getHeaderStyles()

  return (
    <>
      <header
        className={headerStyles.className}
        style={headerStyles.style}
      // {...(theme ? { 'data-theme': theme } : {})}
      >
        <div className="container">
          {renderHeaderStyle()}
        </div>
      </header>
      <MobileMenuDrawer
        isOpen={isMobileMenuOpen}
        onClose={closeMobileMenu}
        navItems={navItems}
        siteSettings={siteSettings}
      />
    </>
  )
}
