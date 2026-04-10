'use client'

import React, { useEffect, useState } from 'react'
import { Home } from 'lucide-react'
import './HomeButton.scss'

interface SiteSettings {
  branding?: {
    favicon?: {
      url?: string
      alt?: string
    }
  }
}

/**
 * Button with site logo/favicon that navigates to home page
 * Displayed at the top of the admin dashboard
 */
const HomeButton: React.FC = () => {
  const [faviconUrl, setFaviconUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchFavicon = async () => {
      try {
        const res = await fetch('/api/globals/site-settings', {
          credentials: 'include',
        })
        
        if (res.ok) {
          const data: SiteSettings = await res.json()
          const url = data?.branding?.favicon?.url
          
          if (url) {
            setFaviconUrl(url)
          }
        }
      } catch (error) {
        console.error('Error fetching site settings:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchFavicon()
  }, [])

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    window.location.href = '/'
  }

  if (loading) {
    return (
      <div className="home-button-wrapper">
        <div className="home-button loading">
          <Home size={24} />
        </div>
      </div>
    )
  }

  return (
    <div className="home-button-wrapper">
      <button 
        onClick={handleClick}
        className="home-button"
        title="Go to Home"
        aria-label="Go to Home"
      >
        {faviconUrl ? (
          <img 
            src={faviconUrl} 
            alt="Site Logo" 
            className="home-button-logo"
          />
        ) : (
          <Home size={24} />
        )}
        <span className="home-button-text">Go to Site</span>
      </button>
    </div>
  )
}

export default HomeButton
