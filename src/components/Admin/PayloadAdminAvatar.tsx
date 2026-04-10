'use client'

import React, { useEffect, useState } from 'react'
import { useAuth, useTheme } from '@payloadcms/ui'
import { Avatar, Dropdown, Button, Label } from '@heroui/react'
import { User, LogOut, LayoutDashboard, Sun, Moon } from 'lucide-react'
import type { User as UserType, UserAvatar as UserAvatarType } from '@/payload-types'

/**
 * Custom avatar component for the Payload admin header.
 * Uses HeroUI Avatar + Dropdown — same look & feel as the frontend.
 *
 * Payload's useAuth returns the user with relationships as IDs (depth 0),
 * so we fetch the full user record to get the populated avatar URL.
 */
const PayloadAdminAvatar: React.FC = () => {
    const { user, logOut } = useAuth<UserType>()
    const { theme, setTheme } = useTheme()
    const [avatarUrl, setAvatarUrl] = useState<string | undefined>(undefined)

    useEffect(() => {
        if (!user) return

        // If avatar is already a populated object, use it directly
        const avatar = user.avatar
        if (avatar && typeof avatar === 'object' && 'url' in avatar) {
            const populated = avatar as UserAvatarType
            const url = populated.sizes?.thumbnail?.url ?? populated.url ?? undefined
            setAvatarUrl(url)
            return
        }

        // If avatar is just an ID (number), fetch the full user with depth
        if (avatar && typeof avatar === 'number') {
            const fetchAvatar = async () => {
                try {
                    const res = await fetch(`/api/user-avatar/${avatar}`, {
                        credentials: 'include',
                    })
                    if (res.ok) {
                        const data = await res.json()
                        setAvatarUrl(data.sizes?.thumbnail?.url ?? data.url ?? undefined)
                    }
                } catch {
                    // silently fall back to placeholder
                }
            }
            fetchAvatar()
        }
    }, [user])

    if (!user) return null

    const handleClickCapture = (e: React.MouseEvent) => {
        // Only prevent the link navigation, don't stop propagation so dropdown still works
        e.preventDefault()
    }

    // Generate initials for fallback
    const getInitials = (name?: string | null) => {
        if (!name) return 'U'
        return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }

    return (
        <div onClickCapture={handleClickCapture}>
            <Dropdown>
                <Button
                    variant="ghost"
                    isIconOnly
                    className="cursor-pointer !ring-0 !border-0 !outline-none !shadow-none p-0"
                >
                    <Avatar size="md" className="!ring-0 !border-0 !outline-none !shadow-none">
                        <Avatar.Image src={avatarUrl} alt={`${user.name ?? 'User'}'s avatar`} />
                        <Avatar.Fallback>{getInitials(user.name)}</Avatar.Fallback>
                    </Avatar>
                </Button>
                <Dropdown.Popover placement="bottom end">
                    <Dropdown.Menu aria-label="User actions" onAction={(key) => {
                        if (key === 'site') window.location.href = '/'
                        if (key === 'account') window.location.href = `/admin/collections/users/${user.id}`
                        if (key === 'theme') setTheme(theme === 'dark' ? 'light' : 'dark')
                        if (key === 'logout') window.location.href = '/logout'
                    }}>
                        <Dropdown.Item id="site" textValue="Go to Site">
                            <LayoutDashboard size={16} />
                            <Label>Go to Site</Label>
                        </Dropdown.Item>
                        <Dropdown.Item id="account" textValue="My Account">
                            <User size={16} />
                            <Label>My Account</Label>
                        </Dropdown.Item>
                        <Dropdown.Item id="theme" textValue="Toggle Theme">
                            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                            <Label>{theme === 'dark' ? 'Light Theme' : 'Dark Theme'}</Label>
                        </Dropdown.Item>
                        <Dropdown.Item id="logout" textValue="Log Out" variant="danger">
                            <LogOut size={16} />
                            <Label>Log Out</Label>
                        </Dropdown.Item>
                    </Dropdown.Menu>
                </Dropdown.Popover>
            </Dropdown>
        </div>
    )
}

export default PayloadAdminAvatar
