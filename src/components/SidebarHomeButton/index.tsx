'use client'

import React, { useEffect, useState } from 'react'
import { Home } from 'lucide-react'
import './styles.scss'

interface SiteSettings {
    branding?: {
        adminLogo?: {
            url?: string
            alt?: string
        }
        favicon?: {
            url?: string
            alt?: string
        }
    }
}

/**
 * Button with site logo/favicon that appears at the top of the admin sidebar
 * Navigates to the home page when clicked
 * Uses Admin Logo if available, otherwise falls back to favicon
 */
const SidebarHomeButton: React.FC = () => {
    const [logoUrl, setLogoUrl] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchLogo = async () => {
            try {
                const res = await fetch('/api/globals/site-settings', {
                    credentials: 'include',
                })

                if (res.ok) {
                    const data: SiteSettings = await res.json()
                    // Use Admin Logo if available, otherwise fall back to favicon
                    const url = data?.branding?.adminLogo?.url || data?.branding?.favicon?.url

                    if (url) {
                        setLogoUrl(url)
                    }
                }
            } catch (error) {
                console.error('Error fetching site settings:', error)
            } finally {
                setLoading(false)
            }
        }

        fetchLogo()
    }, [])

    const handleClick = (e: React.MouseEvent) => {
        e.preventDefault()
        window.open('/', '_blank')
    }

    return (
        <div className="sidebar-home-button-wrapper">
            <button
                onClick={handleClick}
                className="sidebar-home-button"
                title="Go to Site"
                aria-label="Go to Site"
            >
                {logoUrl && !loading ? (
                    <img
                        src={logoUrl}
                        alt="Site Logo"
                        className="sidebar-home-button-logo"
                    />
                ) : (
                    <Home size={32} strokeWidth={1.5} />
                )}
            </button>
        </div>
    )
}

export default SidebarHomeButton
