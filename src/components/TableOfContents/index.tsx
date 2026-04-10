'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { cn } from '@/utilities/ui'
import { toKebabCase } from '@/utilities/toKebabCase'

export type TocPosition = 'left' | 'right' | 'none'

interface TableOfContentsProps {
    className?: string
    position?: TocPosition
}

interface HeadingItem {
    id: string
    text: string
    level: number
}

export default function TableOfContents({ className, position = 'right' }: TableOfContentsProps) {
    const [headings, setHeadings] = useState<HeadingItem[]>([])
    const [activeId, setActiveId] = useState<string>('')

    // Extract headings from the page and add IDs
    useEffect(() => {
        const addIdsToHeadings = () => {
            // Try multiple selectors to find H2 headings
            const selectors = [
                '.payload-richtext h2',
                'article h2',
                'h2',
                '.prose h2'
            ]

            let headingElements: NodeListOf<Element> | null = null
            for (const selector of selectors) {
                headingElements = document.querySelectorAll(selector)
                if (headingElements.length > 0) {
                    console.log(`Found ${headingElements.length} headings with selector: ${selector}`)
                    break
                }
            }

            if (!headingElements || headingElements.length === 0) {
                console.log('No H2 headings found with any selector')
                return
            }

            const headingItems: HeadingItem[] = []

            headingElements.forEach((element) => {
                const text = element.textContent || ''
                if (text.trim()) {
                    const id = toKebabCase(text.trim())
                    element.id = id
                    headingItems.push({
                        id,
                        text: text.trim(),
                        level: 2,
                    })
                    console.log('Added heading:', { id, text: text.trim() })
                }
            })

            setHeadings(headingItems)
            console.log('Total headings set:', headingItems.length)
        }

        // Run immediately
        addIdsToHeadings()

        // Also run after delays to handle dynamic content
        const timer1 = setTimeout(addIdsToHeadings, 500)
        const timer2 = setTimeout(addIdsToHeadings, 1000)

        // Run when page is fully loaded
        const onLoad = () => addIdsToHeadings()
        if (document.readyState === 'complete') {
            onLoad()
        } else {
            window.addEventListener('load', onLoad)
        }

        return () => {
            clearTimeout(timer1)
            clearTimeout(timer2)
            window.removeEventListener('load', onLoad)
        }
    }, [])

    // Handle scroll to update active heading
    const handleScroll = useCallback(() => {
        if (headings.length === 0) return

        const headingElements = headings.map(heading => document.getElementById(heading.id)).filter(Boolean)

        if (headingElements.length === 0) return

        // Find the heading that's currently in view
        let activeHeading = headingElements[0]

        for (const element of headingElements) {
            if (element) {
                const rect = element.getBoundingClientRect()
                // Consider a heading active if it's above the middle of the screen
                if (rect.top <= window.innerHeight / 2) {
                    activeHeading = element
                } else {
                    break
                }
            }
        }

        if (activeHeading && activeHeading.id !== activeId) {
            setActiveId(activeHeading.id)
        }
    }, [headings, activeId])

    useEffect(() => {
        window.addEventListener('scroll', handleScroll, { passive: true })
        // Initial call to set active heading
        handleScroll()

        return () => {
            window.removeEventListener('scroll', handleScroll)
        }
    }, [handleScroll])

    // Smooth scroll to heading
    const scrollToHeading = (id: string) => {
        const element = document.getElementById(id)
        if (element) {
            const headerOffset = 80 // Adjust based on your header height
            const elementPosition = element.getBoundingClientRect().top
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            })
        }
    }

    // Show placeholder when no headings for debugging
    const isDevelopment = process.env.NODE_ENV === 'development'
    const showPlaceholder = isDevelopment && headings.length === 0

    // Always show the component in development for debugging
    if (!isDevelopment && headings.length === 0) {
        return null
    }

    return (
        <nav
            className={cn(
                'sticky top-24 max-h-[calc(100vh-6rem)] overflow-y-auto',
                'rounded border p-4 min-h-[200px]',
                'block', // Always show for debugging
                position === 'left' ? 'lg:order-1' : 'lg:order-2',
                className
            )}
            aria-label="Table of contents"
        >
            <h3 className="text-sm font-semibold text-foreground mb-3 uppercase tracking-wide">
                Contents
            </h3>
            {showPlaceholder ? (
                <div className="text-sm text-muted-foreground">
                    <p>Searching for H2 headings...</p>
                    <p className="text-xs mt-1">Found {headings.length} headings</p>
                    <p className="text-xs mt-1">Position: {position}</p>
                </div>
            ) : headings.length > 0 ? (
                <ul className="space-y-2">
                    {headings.map((heading) => (
                        <li key={heading.id}>
                            <button
                                onClick={() => scrollToHeading(heading.id)}
                                className={cn(
                                    'block w-full text-left text-sm transition-colors duration-200',
                                    'hover:text-primary focus:text-primary focus:outline-none',
                                    'py-1 px-2 rounded',
                                    activeId === heading.id
                                        ? 'text-primary bg-primary/10 font-medium'
                                        : 'text-muted-foreground hover:bg-muted/50'
                                )}
                                aria-current={activeId === heading.id ? 'true' : undefined}
                            >
                                {heading.text}
                            </button>
                        </li>
                    ))}
                </ul>
            ) : (
                <div className="text-sm text-muted-foreground">
                    No headings found
                </div>
            )}
        </nav>
    )
}
