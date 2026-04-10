'use client'

import type { StaticImageData } from 'next/image'
import React, { useEffect, useState } from 'react'
import { cn } from '@/utilities/ui'
import { Media } from '../../components/Media'
import type { Media as MediaType } from '@/payload-types'

type Props = {
    imgClassName?: string
    media?: MediaType | string | number | null
    staticImage?: StaticImageData
    width?: {
        type?: 'full' | 'max' | null
        preset?: 'custom' | '1/2' | '1/3' | '2/3' | '1/4' | '3/4' | null
        maxWidth?: number | null
        alignment?: 'left' | 'center' | 'right' | null
    } | null
    alignment?: 'left' | 'center' | 'right' | null
    aspectRatio?: 'auto' | '16/9' | '4/3' | '1/1' | '3/2' | '2/3' | '21/9' | null
    shadow?: 'none' | 'small' | 'medium' | 'large' | null
    showBorder?: boolean | null
}

export const AnimatedMediaBlock: React.FC<Props> = ({ imgClassName, media, staticImage, width, aspectRatio = 'auto', shadow = 'none', showBorder = true }) => {
    const [isVisible, setIsVisible] = useState(false)

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                const entry = entries[0]
                if (entry && entry.isIntersecting) {
                    setIsVisible(true)
                    observer.disconnect()
                }
            },
            {
                threshold: 0.1,
                rootMargin: '50px 0px -50px 0px',
            }
        )

        const element = document.getElementById('animated-media-block')
        if (element) {
            observer.observe(element)
        }

        return () => observer.disconnect()
    }, [])

    // Determine container classes based on width and alignment
    const getContainerClasses = () => {
        return 'flex items-center justify-center w-full' // Simple flex container with no height constraints
    }

    // Determine image wrapper classes based on width settings
    const getImageWrapperClasses = () => {
        let classes = ''

        // Width classes
        if (width?.type === 'full') {
            classes += 'w-full'
        } else if (width?.type === 'max') {
            // Handle preset widths
            if (width.preset === '1/2') {
                classes += 'w-1/2'
            } else if (width.preset === '1/3') {
                classes += 'w-1/3'
            } else if (width.preset === '2/3') {
                classes += 'w-2/3'
            } else if (width.preset === '1/4') {
                classes += 'w-1/4'
            } else if (width.preset === '3/4') {
                classes += 'w-3/4'
            } else {
                // Custom width
                const maxWidth = width.maxWidth || 896
                classes += `max-w-[${maxWidth}px] w-full`
            }

            // Add alignment for max width (only affects horizontal positioning)
            if (width.alignment === 'left') {
                classes += ' ml-0 mr-auto'
            } else if (width.alignment === 'right') {
                classes += ' ml-auto mr-0'
            } else {
                classes += ' mx-auto'
            }
        } else {
            classes += 'max-w-4xl w-full mx-auto'
        }

        return classes
    }

    // Determine aspect ratio classes
    const getAspectRatioClasses = () => {
        switch (aspectRatio) {
            case '16/9':
                return 'aspect-video'
            case '4/3':
                return 'aspect-[4/3]'
            case '1/1':
                return 'aspect-square'
            case '3/2':
                return 'aspect-[3/2]'
            case '2/3':
                return 'aspect-[2/3]'
            case '21/9':
                return 'aspect-[21/9]'
            case 'auto':
            default:
                return ''
        }
    }

    // Determine shadow classes
    const getShadowClasses = () => {
        switch (shadow) {
            case 'small':
                return 'shadow-sm'
            case 'medium':
                return 'shadow-md'
            case 'large':
                return 'shadow-lg'
            case 'none':
            default:
                return ''
        }
    }

    // Determine border classes
    const getBorderClasses = () => {
        return showBorder ? 'border border-border' : ''
    }

    return (
        <div
            id="animated-media-block"
            className={cn(
                'transform transition-all duration-700 ease-out',
                isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
            )}
        >
            <div className={getContainerClasses()}>
                <div className={cn('relative overflow-hidden rounded-[0.8rem]', getBorderClasses(), getShadowClasses(), getImageWrapperClasses(), getAspectRatioClasses())}>
                    <Media
                        imgClassName={cn('absolute inset-0 w-full h-full object-cover object-center', imgClassName)}
                        resource={media}
                        src={staticImage}
                        fill={true}
                    />
                </div>
            </div>
        </div>
    )
}
