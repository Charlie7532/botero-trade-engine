'use client'

import React, { useEffect } from 'react'

const AdminFavicon: React.FC = () => {
    useEffect(() => {
        // Create favicon link element
        const favicon = document.createElement('link')
        favicon.rel = 'icon'
        favicon.href = '/admin-favicon.ico'

        // Remove existing favicon if any
        const existingFavicon = document.querySelector('link[rel="icon"]')
        if (existingFavicon) {
            existingFavicon.remove()
        }

        // Add the new favicon
        document.head.appendChild(favicon)

        // Cleanup function
        return () => {
            const currentFavicon = document.querySelector('link[rel="icon"][href="/admin-favicon.ico"]')
            if (currentFavicon) {
                currentFavicon.remove()
            }
        }
    }, [])

    return null // This component doesn't render anything visible
}

export default AdminFavicon