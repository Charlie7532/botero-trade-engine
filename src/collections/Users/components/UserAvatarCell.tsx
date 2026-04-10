import React from 'react'
import type { Payload } from 'payload'
import Link from 'next/link'
import { UserAvatar } from './UserAvatar'

type MediaData = {
    id?: number | string
    url?: string
    thumbnailURL?: string
    filename?: string
    alt?: string
    sizes?: {
        thumbnail?: {
            url?: string
        }
        card?: {
            url?: string
        }
    }
}

type UserAvatarCellProps = {
    cellData?: unknown
    rowData?: Record<string, unknown>
    payload?: Payload
}

/**
 * Placeholder component for when there's no avatar
 */
const NoAvatarPlaceholder: React.FC<{ href?: string }> = ({ href }) => {
    const placeholder = (
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
                {placeholder}
            </Link>
        )
    }

    return placeholder
}

/**
 * Extract image URL from various media data formats
 */
function extractImageUrl(data: unknown): string | null {
    if (!data) return null

    // If it's just an ID (number or string), we can't display it without fetching
    if (typeof data === 'number' || typeof data === 'string') {
        return null
    }

    if (typeof data === 'object' && data !== null) {
        const media = data as MediaData

        // Try different URL sources in order of preference
        if (media.sizes?.thumbnail?.url) {
            return media.sizes.thumbnail.url
        }
        if (media.sizes?.card?.url) {
            return media.sizes.card.url
        }
        if (media.thumbnailURL) {
            return media.thumbnailURL
        }
        if (media.url) {
            return media.url
        }
    }

    return null
}

/**
 * Custom server cell component for displaying user avatars in the list view.
 * As a server component, it can fetch media data if only an ID is provided.
 */
export const UserAvatarCell: React.FC<UserAvatarCellProps> = async ({
    cellData,
    rowData,
    payload,
}) => {
    // Get user ID for the link
    const userId = rowData?.id as number | string | undefined
    const href = userId ? `/admin/collections/users/${userId}` : undefined

    // Try to get image URL from cellData first, then fallback to rowData.avatar
    let imageUrl = extractImageUrl(cellData) || extractImageUrl(rowData?.avatar)
    let altText = 'User avatar'

    // If we only have an ID and have payload, fetch the media
    if (!imageUrl && payload) {
        const mediaId = typeof cellData === 'number' || typeof cellData === 'string'
            ? cellData
            : typeof rowData?.avatar === 'number' || typeof rowData?.avatar === 'string'
                ? rowData.avatar
                : null

        if (mediaId) {
            try {
                const media = await payload.findByID({
                    collection: 'user-avatar',
                    id: mediaId as number,
                    depth: 0,
                })
                if (media) {
                    imageUrl = extractImageUrl(media)
                    if (media.alt) altText = media.alt
                    else if (media.filename) altText = media.filename
                }
            } catch {
                // Media not found, will show placeholder
            }
        }
    }

    // Extract alt text if available from populated data
    if (cellData && typeof cellData === 'object' && cellData !== null) {
        const media = cellData as MediaData
        if (media.alt) altText = media.alt
        else if (media.filename) altText = media.filename
    }

    // Use nickname or name for alt text if available
    if (rowData?.nickname) {
        altText = `${rowData.nickname} avatar`
    } else if (rowData?.name) {
        altText = `${rowData.name} avatar`
    }

    if (!imageUrl) {
        return <NoAvatarPlaceholder href={href} />
    }

    return <UserAvatar src={imageUrl} alt={altText} href={href} />
}
