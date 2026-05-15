'use client'

import React, { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { Avatar, Dropdown, Button, Label } from '@heroui/react'
import { LogOut, Settings, ChevronsUpDown, ShieldCheck } from 'lucide-react'

import type { User, UserAvatar as UserAvatarType } from '@/payload-types'

type Props = {
  user: Pick<User, 'id' | 'name' | 'email' | 'avatar' | 'role'>
  /** Fallback portfolio slug to use when no slug is in the URL. */
  fallbackSlug?: string
}

const getInitials = (name?: string | null, email?: string) => {
  if (name) return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
  if (email) return email.slice(0, 2).toUpperCase()
  return 'U'
}

const SidebarUser: React.FC<Props> = ({ user, fallbackSlug }) => {
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>(undefined)
  const pathname = usePathname() ?? ''
  const slugMatch = pathname.match(/^\/portafolio\/([^/]+)/)
  const activeSlug = slugMatch?.[1] ?? fallbackSlug
  const isAdmin = user.role === 'admin' || user.role === 'superadmin'

  useEffect(() => {
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
        } catch {
          // fall back to initials
        }
      }
      fetchAvatar()
    }
  }, [user.avatar])

  return (
    <Dropdown>
      <Button
        variant="ghost"
        className="!w-full !justify-start gap-3 px-2 py-2 h-auto rounded-lg hover:bg-surface-secondary"
      >
        <Avatar size="sm" className="shrink-0">
          <Avatar.Image src={avatarUrl} alt={`${user.name ?? user.email}'s avatar`} />
          <Avatar.Fallback>{getInitials(user.name, user.email)}</Avatar.Fallback>
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col items-start text-left">
          <span className="truncate text-sm font-medium text-foreground leading-tight">
            {user.name ?? user.email}
          </span>
          <span className="truncate text-xs text-muted leading-tight">{user.email}</span>
        </div>
        <ChevronsUpDown size={14} className="ml-auto shrink-0 text-muted" />
      </Button>
      <Dropdown.Popover placement="top end">
        <Dropdown.Menu
          aria-label="User actions"
          onAction={(key) => {
            if (key === 'account') {
              window.location.href = activeSlug
                ? `/portafolio/${activeSlug}/settings`
                : '/portafolio'
            }
            if (key === 'admin') window.location.href = '/admin'
            if (key === 'logout') window.location.href = '/logout'
          }}
        >
          <Dropdown.Item id="account" textValue="Account Settings">
            <Settings size={16} />
            <Label>Account Settings</Label>
          </Dropdown.Item>
          {isAdmin ? (
            <Dropdown.Item id="admin" textValue="Admin Panel">
              <ShieldCheck size={16} />
              <Label>Admin Panel</Label>
            </Dropdown.Item>
          ) : null}
          <Dropdown.Item id="logout" textValue="Log Out" variant="danger">
            <LogOut size={16} />
            <Label>Log Out</Label>
          </Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown.Popover>
    </Dropdown>
  )
}

export default SidebarUser
