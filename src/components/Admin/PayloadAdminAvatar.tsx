'use client'

import React, { useEffect, useRef, useState } from 'react'
import { useAuth, useTheme } from '@payloadcms/ui'
import { User, LogOut, LayoutDashboard, Sun, Moon, ChevronRight } from 'lucide-react'
import type { User as UserType, UserAvatar as UserAvatarType } from '@/payload-types'

/**
 * Custom avatar component for the Payload admin header.
 * Minimalist Apple-style dropdown using project CSS variables.
 * 
 * Includes fix for Payload's default link behavior by preventing event propagation.
 */
const PayloadAdminAvatar: React.FC = () => {
    const { user, logOut } = useAuth<UserType>()
    const { theme, setTheme } = useTheme()
    const [avatarUrl, setAvatarUrl] = useState<string | undefined>(undefined)
    const [open, setOpen] = useState(false)
    const [hovered, setHovered] = useState<string | null>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    // Fetch avatar URL
    useEffect(() => {
        if (!user) return
        const avatar = user.avatar
        if (avatar && typeof avatar === 'object' && 'url' in avatar) {
            const populated = avatar as UserAvatarType
            setAvatarUrl(populated.sizes?.thumbnail?.url ?? populated.url ?? undefined)
            return
        }
        if (avatar && typeof avatar === 'number') {
            const fetchAvatar = async () => {
                try {
                    const res = await fetch(`/api/user-avatar/${avatar}`, { credentials: 'include' })
                    if (res.ok) {
                        const data = await res.json()
                        setAvatarUrl(data.sizes?.thumbnail?.url ?? data.url ?? undefined)
                    }
                } catch { /* silently fall back */ }
            }
            fetchAvatar()
        }
    }, [user])

    // Close on outside click
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    if (!user) return null

    const initials = (name?: string | null) => {
        if (!name) return 'U'
        return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }

    const isDark = theme === 'dark'

    const items = [
        { key: 'site',    icon: <LayoutDashboard size={14} />, label: 'Go to Site',     danger: false },
        { key: 'account', icon: <User size={14} />,            label: 'My Account',     danger: false },
        { key: 'theme',   icon: isDark ? <Sun size={14} /> : <Moon size={14} />,
                          label: isDark ? 'Light Theme' : 'Dark Theme',                 danger: false },
    ]
    const logoutItem = { key: 'logout', icon: <LogOut size={14} />, label: 'Log Out', danger: true }

    const handleAction = (key: string) => {
        setOpen(false)
        if (key === 'site')    window.location.href = '/'
        if (key === 'account') window.location.href = `/admin/collections/users/${user.id}`
        if (key === 'theme')   setTheme(isDark ? 'light' : 'dark')
        if (key === 'logout')  window.location.href = '/logout'
    }

    return (
        <div ref={containerRef} style={{ position: 'relative', display: 'inline-flex' }}>

            {/* ── Avatar trigger ── */}
            <button
                onClick={(e) => {
                    // CRITICAL: Stop propagation and prevent default to stop Payload from navigating to /admin/account
                    e.preventDefault();
                    e.stopPropagation();
                    setOpen(o => !o);
                }}
                style={{
                    all: 'unset',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '4px',
                    borderRadius: '999px',
                    transition: 'opacity 0.15s ease',
                    opacity: open ? 0.7 : 1,
                }}
                aria-label="Open user menu"
                aria-expanded={open}
            >
                {/* Avatar circle */}
                <span style={{
                    width: 30,
                    height: 30,
                    borderRadius: '50px', // Squircle/Apple style instead of full circle
                    background: 'var(--accent)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden',
                    flexShrink: 0,
                    boxShadow: '0 0 0 2px var(--background), 0 0 0 3px var(--border)',
                    transition: 'box-shadow 0.2s ease',
                }}>
                    {avatarUrl ? (
                        <img
                            src={avatarUrl}
                            alt={`${user.name ?? 'User'}'s avatar`}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                    ) : (
                        <span style={{
                            fontSize: 11,
                            fontWeight: 600,
                            color: 'var(--accent-foreground)',
                            letterSpacing: '0.02em',
                            fontFamily: 'var(--font-sans, system-ui)',
                        }}>
                            {initials(user.name)}
                        </span>
                    )}
                </span>
            </button>

            {/* ── Dropdown panel ── */}
            <div
                style={{
                    position: 'absolute',
                    top: 'calc(100% + 10px)',
                    right: 0,
                    width: 220,
                    borderRadius: 14,
                    overflow: 'hidden',
                    background: isDark
                        ? 'oklch(18% 0.014 238.89 / 0.9)'
                        : 'oklch(99% 0.005 238.89 / 0.92)',
                    backdropFilter: 'blur(24px) saturate(180%)',
                    WebkitBackdropFilter: 'blur(24px) saturate(180%)',
                    border: '1px solid var(--border)',
                    boxShadow: isDark
                        ? '0 20px 60px -10px rgba(0,0,0,0.6), 0 4px 16px -4px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)'
                        : '0 20px 60px -10px rgba(0,0,0,0.14), 0 4px 16px -4px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
                    transformOrigin: 'top right',
                    transform: open ? 'scale(1) translateY(0)' : 'scale(0.94) translateY(-6px)',
                    opacity: open ? 1 : 0,
                    pointerEvents: open ? 'auto' : 'none',
                    transition: 'transform 0.2s cubic-bezier(0.34,1.56,0.64,1), opacity 0.15s ease',
                    zIndex: 9999,
                }}
                role="menu"
                aria-label="User menu"
            >

                {/* ── User info header ── */}
                <div style={{
                    padding: '14px 16px 12px',
                    borderBottom: '1px solid var(--separator)',
                }}>
                    <div style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--foreground)',
                        fontFamily: 'var(--font-sans, system-ui)',
                        lineHeight: 1.3,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}>
                        {user.name ?? 'User'}
                    </div>
                    <div style={{
                        fontSize: 11,
                        color: 'var(--muted)',
                        fontFamily: 'var(--font-sans, system-ui)',
                        marginTop: 2,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}>
                        {user.email}
                    </div>
                </div>

                {/* ── Main items ── */}
                <div style={{ padding: '6px 0' }}>
                    {items.map(item => (
                        <button
                            key={item.key}
                            role="menuitem"
                            onClick={() => handleAction(item.key)}
                            onMouseEnter={() => setHovered(item.key)}
                            onMouseLeave={() => setHovered(null)}
                            style={{
                                all: 'unset',
                                width: '100%',
                                boxSizing: 'border-box',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 10,
                                padding: '8px 16px',
                                cursor: 'pointer',
                                fontFamily: 'var(--font-sans, system-ui)',
                                fontSize: 13,
                                fontWeight: 400,
                                color: hovered === item.key ? 'var(--foreground)' : 'var(--foreground)',
                                background: hovered === item.key
                                    ? isDark ? 'oklch(30% 0.014 238.89)' : 'oklch(93% 0.011 238.89)'
                                    : 'transparent',
                                transition: 'background 0.12s ease',
                                letterSpacing: '-0.01em',
                            }}
                        >
                            <span style={{
                                color: 'var(--muted)',
                                display: 'flex',
                                alignItems: 'center',
                                flexShrink: 0,
                            }}>
                                {item.icon}
                            </span>
                            <span style={{ flex: 1 }}>{item.label}</span>
                            <ChevronRight
                                size={12}
                                style={{
                                    color: 'var(--muted)',
                                    opacity: hovered === item.key ? 0.6 : 0,
                                    transition: 'opacity 0.12s ease',
                                }}
                            />
                        </button>
                    ))}
                </div>

                {/* ── Separator ── */}
                <div style={{ height: 1, background: 'var(--separator)', margin: '0 16px' }} />

                {/* ── Logout ── */}
                <div style={{ padding: '6px 0' }}>
                    <button
                        role="menuitem"
                        onClick={() => handleAction('logout')}
                        onMouseEnter={() => setHovered('logout')}
                        onMouseLeave={() => setHovered(null)}
                        style={{
                            all: 'unset',
                            width: '100%',
                            boxSizing: 'border-box',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 10,
                            padding: '8px 16px',
                            cursor: 'pointer',
                            fontFamily: 'var(--font-sans, system-ui)',
                            fontSize: 13,
                            fontWeight: 400,
                            color: hovered === 'logout'
                                ? 'var(--danger)'
                                : 'var(--danger)',
                            background: hovered === 'logout'
                                ? isDark ? 'oklch(30% 0.014 238.89)' : 'oklch(93% 0.011 238.89)'
                                : 'transparent',
                            transition: 'background 0.12s ease',
                            letterSpacing: '-0.01em',
                        }}
                    >
                        <span style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                            {logoutItem.icon}
                        </span>
                        <span style={{ flex: 1 }}>{logoutItem.label}</span>
                    </button>
                </div>

            </div>
        </div>
    )
}

export default PayloadAdminAvatar
