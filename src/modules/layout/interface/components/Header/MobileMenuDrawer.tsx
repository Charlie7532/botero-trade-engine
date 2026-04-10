'use client'

import React, { useEffect } from 'react'
import { CMSLink } from '@/components/Link'
import Link from 'next/link'
import { IconThemeSwitch } from '@/components/ui/IconThemeSwitch'
import { SocialMediaIcon } from '@/components/SocialMediaIcons'
import type { Header } from '@/payload-types'
import type { SiteSettings } from '@/utilities/getSiteSettings'

interface MobileMenuDrawerProps {
    isOpen: boolean
    onClose: () => void
    navItems: Header['navItems']
    siteSettings?: SiteSettings
}

export const MobileMenuDrawer: React.FC<MobileMenuDrawerProps> = ({
    isOpen,
    onClose,
    navItems = [],
    siteSettings
}) => {
    // Close menu on escape key
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose()
        }

        if (isOpen) {
            document.addEventListener('keydown', handleEscape)
            // Prevent body scroll when menu is open
            document.body.style.overflow = 'hidden'
            document.body.style.overflowX = 'hidden'
        }

        return () => {
            document.removeEventListener('keydown', handleEscape)
            // Only reset if document.body still exists
            if (document.body) {
                document.body.style.overflow = 'unset'
                document.body.style.overflowX = 'unset'
            }
        }
    }, [isOpen, onClose])

    return (
        <>
            {/* Backdrop */}
            <div
                className={`fixed inset-0 bg-black bg-opacity-50 z-40 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
                    }`}
                onClick={onClose}
            />

            {/* Drawer */}
            <div
                className={`fixed top-0 right-0 h-full w-72 max-w-[75vw] bg-white dark:bg-gray-900 shadow-xl z-40 transform transition-transform duration-300 ease-in-out flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'
                    }`}
                style={{
                    paddingTop: 'calc(var(--payload-admin-bar-height, 0px) + 80px)',
                    maxWidth: 'min(18rem, 75vw)' // Ensure it never exceeds viewport
                }}
            >
                {/* Scrollable Content */}
                <div className="flex-1 overflow-y-auto">
                    {/* Navigation Items */}
                    <nav className="p-6">
                        {navItems && navItems.length > 0 ? (
                            <ul className="space-y-4">
                                {navItems.map(({ link }, i) => (
                                    <li key={i} onClick={onClose}>
                                        <CMSLink
                                            className="block py-3 px-4 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-secondary-500 dark:hover:text-secondary-400 rounded-md transition-colors"
                                            {...link}
                                        />
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                                No navigation items configured
                            </p>
                        )}
                    </nav>

                    {/* Theme Switch - Bottom of scrollable content */}
                    <div className="p-6 border-t border-gray-200 dark:border-gray-700">
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-500 dark:text-gray-400">Theme</span>
                            <IconThemeSwitch />
                        </div>
                    </div>


                    {/* Social Media Icons */}
                    {siteSettings?.socialMedia?.platforms && siteSettings.socialMedia.platforms.length > 0 && (
                        <div className="p-6 border-t border-gray-200 dark:border-gray-700">
                            <div className="flex flex-wrap justify-center gap-3">
                                {siteSettings.socialMedia.platforms.map((item: { platform: string; url: string }, index: number) => (
                                    <div key={index} className="flex-grow flex justify-center min-w-0 max-w-[60px]">
                                        <a
                                            href={item.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="group w-9 h-9 rounded-full border border-gray-300 dark:border-gray-600 flex justify-center items-center transition-all duration-300 hover:text-secondary-500 hover:border-secondary-500"
                                            aria-label={`Follow us on ${item.platform}`}
                                        >
                                            <SocialMediaIcon
                                                platform={item.platform}
                                                className="w-4 h-4 text-gray-600 dark:text-gray-400 transition-all duration-300 group-hover:text-secondary-500"
                                            />
                                        </a>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Fixed Footer with Legal Links */}
                <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
                    <div className="flex text-sm">
                        {siteSettings?.legalPolicies && siteSettings.legalPolicies.length > 0 ? (
                            siteSettings.legalPolicies.length >= 4 ? (
                                // 4 or more: show first 2 and Other policies link
                                <>
                                    {siteSettings.legalPolicies.slice(0, 2).map((policy: any, i: number) => (
                                        <div key={i} className={`flex-1 text-center ${i === 1 ? 'border-l border-gray-200 dark:border-gray-700' : ''}`}>
                                            <CMSLink
                                                className="block py-4 text-gray-500 dark:text-gray-400 hover:text-secondary-500 dark:hover:text-secondary-400 transition-colors"
                                                {...{
                                                    ...policy,
                                                    label: policy.label || policy.name,
                                                }}
                                                onClick={onClose}
                                            />
                                        </div>
                                    ))}

                                    <div className="flex-1 text-center border-l border-gray-200 dark:border-gray-700">
                                        <Link href="/legal-policies" className="block py-4 text-gray-500 dark:text-gray-400 hover:text-secondary-500 dark:hover:text-secondary-400 transition-colors" onClick={onClose}>
                                            Other policies
                                        </Link>
                                    </div>
                                </>
                            ) : (
                                // 1-3: show them all
                                siteSettings.legalPolicies.map((policy: any, i: number) => (
                                    <div key={i} className={`flex-1 text-center ${i !== 0 ? 'border-l border-gray-200 dark:border-gray-700' : ''}`}>
                                        <CMSLink
                                            className="block py-4 text-gray-500 dark:text-gray-400 hover:text-secondary-500 dark:hover:text-secondary-400 transition-colors"
                                            {...{
                                                ...policy,
                                                label: policy.label || policy.name,
                                            }}
                                            onClick={onClose}
                                        />
                                    </div>
                                ))
                            )
                        ) : null}
                    </div>
                </div>
            </div>
        </>
    )
}