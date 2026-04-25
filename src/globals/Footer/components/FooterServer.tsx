import { getCachedGlobal } from '@/utilities/getGlobals'
import { getCachedSiteSettings } from '@/utilities/getSiteSettings'
import Link from 'next/link'
import React from 'react'

import type { Footer } from '@/payload-types'

import { CMSLink } from '@/components/Link'
import { EnhancedConfigurableLogo } from '@/components/ConfigurableLogo/EnhancedConfigurableLogo.server'
import { SocialMediaLinks } from '@/components/SocialMediaIcons'
import { IconThemeSwitch } from '@/components/ui/IconThemeSwitch'

export async function Footer() {
  const footerData: Footer = await getCachedGlobal('footer', 1)()
  const siteSettings = await getCachedSiteSettings(1)()

  const navItems = footerData?.navItems || []
  const socialMediaPlatforms = siteSettings?.socialMedia?.platforms || []
  const legalPolicies = siteSettings?.legalPolicies || []
  const siteName = siteSettings?.branding?.siteName || 'Your Site'
  const currentYear = new Date().getFullYear()

  return (
    <footer className="pt-6 w-full">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="py-10 flex justify-between items-center flex-col gap-8 xl:flex-row">
          <div className="flex items-center flex-col xl:flex-row">
            <Link href="/" className="flex justify-center mb-8 xl:mb-0">
              <EnhancedConfigurableLogo context="footer" />
            </Link>

            {navItems.length > 0 && (
              <div className="py-8 xl:border-l border-gray-200 xl:ml-11 xl:pl-11 transition-all duration-500">
                <ul className={`
                  text-lg transition-all duration-500
                  ${navItems.length <= 4
                    ? `flex items-center flex-col md:flex-row gap-6 md:gap-12`
                    : `flex flex-wrap items-center justify-center md:justify-start gap-4 md:gap-6`
                  }
                `}>
                  {navItems.map(({ link }, i) => (
                    <li key={i} className={navItems.length > 4 ? 'flex-grow text-center md:text-left' : ''}>
                      <CMSLink
                        className="text-gray-800 hover:text-secondary-500 dark:text-gray-200 dark:hover:text-secondary-400"
                        {...link}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Social Media Links and Theme Switch */}
          <div className="flex items-center space-x-4 sm:justify-center">
            {/* Social Media Links */}
            {socialMediaPlatforms.length > 0 && (
              <SocialMediaLinks
                socialMediaItems={socialMediaPlatforms}
                className="flex space-x-4"
                iconClassName="w-4 h-4 text-gray-700 transition-all duration-500 group-hover:text-secondary-500"
              />
            )}

            {/* Theme Switch */}
            <IconThemeSwitch />
          </div>
        </div>

        <div className="py-7 border-t border-gray-200">
          <div className="flex flex-col md:flex-row justify-between">
            <div className="w-full text-center md:text-left">
              <p className="mb-2 text-gray-400">&copy; {currentYear} {siteName}. All rights reserved.</p>
              <div className="text-sm">
                <span className="text-gray-400">Powered by </span>
                <Link
                  href="https://main12.com/"
                  className="text-blue-400 hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Main 12
                </Link>
              </div>
            </div>

            {/* Legal Links */}
            {legalPolicies.length > 0 && (
              <div className="w-full text-center md:text-right text-gray-400 mt-4 md:mt-0">
                {legalPolicies.length >= 4 ? (
                  // 4 or more: show first 2 and an Other policies link
                  <>
                    {legalPolicies.slice(0, 2).map((policy: any, idx: number) => (
                      <span key={idx}>
                        <CMSLink
                          className="hover:underline mx-2 text-gray-400"
                          {...{
                            ...policy,
                            label: policy.label || policy.name,
                          }}
                        />
                        {idx === 0 && " | "}
                      </span>
                    ))}
                    <span className="mx-2">|</span>
                    <Link href="/legal-policies" className="hover:underline mx-2 text-gray-400">
                      Other policies
                    </Link>
                  </>
                ) : (
                  // 1-3: show them all
                  legalPolicies.map((policy: any, idx: number) => (
                    <span key={idx}>
                      <CMSLink
                        className="hover:underline mx-2 text-gray-400"
                        {...{
                          ...policy,
                          label: policy.label || policy.name,
                        }}
                      />
                      {idx !== legalPolicies.length - 1 && " | "}
                    </span>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </footer>
  )
}
