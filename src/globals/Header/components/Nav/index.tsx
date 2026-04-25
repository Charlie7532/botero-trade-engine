'use client'

import React from 'react'

import type { Header as HeaderType } from '@/payload-types'

import { CMSLink } from '@/components/Link'
import Link from 'next/link'
import { SearchIcon, User, ArrowRight, ExternalLink, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

// Google Icon SVG Component
const GoogleIcon = () => (
  <svg className="w-4 h-4" xmlns="http://www.w3.org/2000/svg" viewBox="-0.5 0 48 48" version="1.1">
    <g id="Icons" stroke="none" strokeWidth="1" fill="none" fillRule="evenodd">
      <g id="Color-" transform="translate(-401.000000, -860.000000)">
        <g id="Google" transform="translate(401.000000, 860.000000)">
          <path d="M9.82727273,24 C9.82727273,22.4757333 10.0804318,21.0144 10.5322727,19.6437333 L2.62345455,13.6042667 C1.08206818,16.7338667 0.213636364,20.2602667 0.213636364,24 C0.213636364,27.7365333 1.081,31.2608 2.62025,34.3882667 L10.5247955,28.3370667 C10.0772273,26.9728 9.82727273,25.5168 9.82727273,24" id="Fill-1" fill="#FBBC05" />
          <path d="M23.7136364,10.1333333 C27.025,10.1333333 30.0159091,11.3066667 32.3659091,13.2266667 L39.2022727,6.4 C35.0363636,2.77333333 29.6954545,0.533333333 23.7136364,0.533333333 C14.4268636,0.533333333 6.44540909,5.84426667 2.62345455,13.6042667 L10.5322727,19.6437333 C12.3545909,14.112 17.5491591,10.1333333 23.7136364,10.1333333" id="Fill-2" fill="#EB4335" />
          <path d="M23.7136364,37.8666667 C17.5491591,37.8666667 12.3545909,33.888 10.5322727,28.3562667 L2.62345455,34.3946667 C6.44540909,42.1557333 14.4268636,47.4666667 23.7136364,47.4666667 C29.4455,47.4666667 34.9177955,45.4314667 39.0249545,41.6181333 L31.5177727,35.8144 C29.3995682,37.1488 26.7323182,37.8666667 23.7136364,37.8666667" id="Fill-3" fill="#34A853" />
          <path d="M46.1454545,24 C46.1454545,22.6133333 45.9318182,21.12 45.6113636,19.7333333 L23.7136364,19.7333333 L23.7136364,28.8 L36.3181818,28.8 C35.6879545,31.8912 33.9724545,34.2677333 31.5177727,35.8144 L39.0249545,41.6181333 C43.3393409,37.6138667 46.1454545,31.6490667 46.1454545,24" id="Fill-4" fill="#4285F4" />
        </g>
      </g>
    </g>
  </svg>
)

// Email Icon SVG Component
const EmailIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
)

interface HeaderNavProps {
  data: HeaderType
}

export const HeaderNav: React.FC<HeaderNavProps> = ({ data }) => {
  const navItems = data?.navItems || []
  const menuPosition = (data as any)?.menuPosition || 'right'
  const showSearchBar = (data as any)?.showSearchBar !== false // Default to true
  const buttons = (data as any)?.buttons || []

  // Get text color styling to ensure consistency with header
  const getTextColorStyles = () => {
    const textColor = (data as any)?.textColor || 'auto'
    let textClasses = ''
    let linkClasses = ''
    const style: React.CSSProperties = {}

    switch (textColor) {
      case 'primary':
        textClasses = 'text-primary'
        linkClasses = 'text-primary hover:text-primary/80'
        break
      case 'custom':
        const customColor = (data as any)?.customTextColor
        if (customColor) {
          style.color = customColor
          textClasses = ''
          linkClasses = `hover:opacity-80`
        } else {
          textClasses = 'text-gray-900 dark:text-white'
          linkClasses = 'text-gray-900 hover:text-gray-700 dark:text-white dark:hover:text-gray-200'
        }
        break
      case 'auto':
      default:
        // Auto should be black in light theme, white in dark theme
        textClasses = 'text-gray-900 dark:text-white'
        linkClasses = 'text-gray-900 hover:text-gray-700 dark:text-white dark:hover:text-gray-200'
        break
    }

    return { textClasses, linkClasses, style }
  }

  const { textClasses, linkClasses, style: textStyle } = getTextColorStyles()

  // Get icon component based on icon type
  const getIcon = (iconType: string) => {
    const iconProps = { className: "w-4 h-4" }

    switch (iconType) {
      case 'google':
        return <GoogleIcon />
      case 'email':
        return <EmailIcon />
      case 'search':
        return <SearchIcon {...iconProps} />
      case 'user':
        return <User {...iconProps} />
      case 'arrow-right':
        return <ArrowRight {...iconProps} />
      case 'external-link':
        return <ExternalLink {...iconProps} />
      case 'chevron-right':
        return <ChevronRight {...iconProps} />
      default:
        return null
    }
  }

  // Get layout structure based on menuPosition
  const getLayoutClasses = () => {
    switch (menuPosition) {
      case 'left':
        return {
          container: 'ml-6 flex items-center w-full justify-between',
          menuSection: 'flex gap-3 items-center',
          widgetsSection: 'flex gap-3 items-center ml-auto'
        }
      case 'center':
        return {
          container: 'flex items-center w-full',
          menuSection: 'flex gap-3 items-center mx-auto',
          widgetsSection: 'flex gap-3 items-center ml-4'
        }
      case 'right':
      default:
        return {
          container: 'flex items-center w-full justify-end',
          menuSection: 'flex gap-3 items-center',
          widgetsSection: 'flex gap-3 items-center ml-4'
        }
    }
  }

  const layoutClasses = getLayoutClasses()

  return (
    <nav className={`${layoutClasses.container} ${textClasses}`} style={textStyle}>
      <div id="menu" className={layoutClasses.menuSection}>
        {navItems.map(({ link }, i) => {
          return <CMSLink key={i} {...link} appearance="link" className={`transition-all duration-200 ${linkClasses}`} />
        })}
      </div>
      <div id="widgets" className={layoutClasses.widgetsSection}>
        {showSearchBar && (
          <Link href="/search" className={`transition-all duration-200 ${linkClasses}`}>
            <span className="sr-only">Search</span>
            <SearchIcon className="w-5 h-5" />
          </Link>
        )}

        {/* Configurable Buttons */}
        {buttons && buttons.length > 0 && (
          <div className="flex gap-2 items-center">
            {buttons.map((button: any, i: number) => {
              // Determine button variant
              let variant: "default" | "secondary" | "outline" | "link" = "default"

              if (button.style === 'default' || button.style === 'primary') {
                variant = "default"
              } else if (button.style === 'secondary') {
                variant = "secondary"
              } else if (button.style === 'outline') {
                variant = "outline"
              } else if (button.style === 'link') {
                variant = "link"
              }

              // Get icon component
              const iconComponent = button.icon && button.icon !== 'none' ? getIcon(button.icon) : null
              const iconPosition = button.iconPosition || 'before'

              // Determine button content based on icon position
              const renderButtonContent = () => {
                if (!iconComponent) {
                  return button.label
                }

                switch (iconPosition) {
                  case 'before':
                    return (
                      <>
                        <span className="mr-2">{iconComponent}</span>
                        {button.label}
                      </>
                    )
                  case 'after':
                    return (
                      <>
                        {button.label}
                        <span className="ml-2">{iconComponent}</span>
                      </>
                    )
                  case 'only':
                    return (
                      <span title={button.label}>
                        {iconComponent}
                      </span>
                    )
                  default:
                    return button.label
                }
              }

              return (
                <CMSLink
                  key={i}
                  type={button.type}
                  reference={button.reference}
                  url={button.url}
                >
                  <Button
                    variant={variant}
                    size="sm"
                    className={`text-sm ${iconPosition === 'only' ? 'px-2' : ''}`}
                  >
                    {renderButtonContent()}
                  </Button>
                </CMSLink>
              )
            })}
          </div>
        )}
      </div>
    </nav>
  )
}