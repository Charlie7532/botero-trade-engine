'use client'

import { useEffect } from 'react'

export default function ForceLightTheme() {
    useEffect(() => {
        const html = document.documentElement
        const body = document.body
        const prevTheme = html.getAttribute('data-theme')
        const hadDarkClass = body.classList.contains('dark')
        const hadLightClass = body.classList.contains('light')

        html.setAttribute('data-theme', 'light')
        body.setAttribute('data-theme', 'light')
        body.classList.remove('dark')
        body.classList.add('light')

        return () => {
            if (prevTheme) {
                html.setAttribute('data-theme', prevTheme)
                body.setAttribute('data-theme', prevTheme)
            } else {
                html.removeAttribute('data-theme')
                body.removeAttribute('data-theme')
            }
            body.classList.toggle('dark', hadDarkClass)
            body.classList.toggle('light', hadLightClass)
        }
    }, [])

    return null
}
