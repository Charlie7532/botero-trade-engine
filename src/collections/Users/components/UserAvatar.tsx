'use client'
import React, { useState } from 'react'
import Link from 'next/link'

interface UserAvatarProps {
    src: string
    alt: string
    href?: string
}

/**
 * Client component for displaying user avatar with error handling.
 * Shows a placeholder with user icon when image fails to load.
 * Displays as a circle/rounded avatar.
 */
export const UserAvatar: React.FC<UserAvatarProps> = ({ src, alt, href }) => {
    const [hasError, setHasError] = useState(false)
    const [isLoading, setIsLoading] = useState(true)

    const content = hasError ? (
        <div
            style={{
                width: '40px',
                height: '40px',
                backgroundColor: 'var(--theme-elevation-150)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--theme-elevation-400)',
            }}
        >
            {/* User icon placeholder */}
            <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            >
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
            </svg>
        </div>
    ) : (
        <div
            style={{
                width: '40px',
                height: '40px',
                overflow: 'hidden',
                borderRadius: '50%',
                position: 'relative',
                backgroundColor: isLoading ? 'var(--theme-elevation-100)' : 'transparent',
            }}
        >
            {/* Skeleton loader */}
            {isLoading && (
                <div
                    style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        backgroundColor: 'var(--theme-elevation-100)',
                        borderRadius: '50%',
                        overflow: 'hidden',
                    }}
                >
                    <div
                        style={{
                            width: '100%',
                            height: '100%',
                            background:
                                'linear-gradient(90deg, var(--theme-elevation-100) 25%, var(--theme-elevation-150) 50%, var(--theme-elevation-100) 75%)',
                            backgroundSize: '200% 100%',
                            animation: 'shimmer 1.5s infinite',
                        }}
                    />
                    <style>
                        {`
                            @keyframes shimmer {
                                0% { background-position: 200% 0; }
                                100% { background-position: -200% 0; }
                            }
                        `}
                    </style>
                </div>
            )}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={src}
                alt={alt}
                onLoad={() => setIsLoading(false)}
                onError={() => {
                    setIsLoading(false)
                    setHasError(true)
                }}
                style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    opacity: isLoading ? 0 : 1,
                    transition: 'opacity 0.2s ease-in-out',
                }}
            />
        </div>
    )

    if (href) {
        return (
            <Link
                href={href}
                style={{
                    display: 'block',
                    textDecoration: 'none',
                    cursor: 'pointer',
                }}
            >
                {content}
            </Link>
        )
    }

    return content
}
