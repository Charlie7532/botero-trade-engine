'use client'

import Image from 'next/image'
import { useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'

type Props = {
  userId: number | string
  name: string | null | undefined
  nickname: string | null | undefined
  preferredLanguage: string | null | undefined
  email: string
  avatarUrl: string | null | undefined
}

export default function ProfileForm({
  userId,
  name,
  nickname,
  preferredLanguage,
  email,
  avatarUrl,
}: Props) {
  const [preview, setPreview] = useState<string | null>(avatarUrl ?? null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const [isUploading, startUpload] = useTransition()
  const fileRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setAvatarError(null)

    startUpload(async () => {
      // Upload file to Payload media collection
      const fd = new FormData()
      fd.append('file', file)
      fd.append('alt', `avatar-${userId}`)

      const uploadRes = await fetch('/api/user-avatar', {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })

      if (!uploadRes.ok) {
        setAvatarError('Upload failed.')
        setPreview(avatarUrl ?? null)
        return
      }

      const { doc } = await uploadRes.json()

      // Link the uploaded media to the user
      const patchRes = await fetch(`/api/users/${userId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ avatar: doc.id }),
      })

      if (!patchRes.ok) {
        setAvatarError('Failed to save avatar.')
        setPreview(avatarUrl ?? null)
      } else {
        router.refresh()
      }
    })
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setSuccess(false)
    const fd = new FormData(e.currentTarget)
    const name = (fd.get('name') as string ?? '').trim()
    const nickname = (fd.get('nickname') as string ?? '').trim()
    const preferredLanguage = fd.get('preferredLanguage') as string

    if (!name) return setError('Name cannot be empty.')
    if (name.length > 80) return setError('Name must be 80 characters or fewer.')
    if (nickname.length > 40) return setError('Nickname must be 40 characters or fewer.')

    startTransition(async () => {
      const res = await fetch(`/api/users/${userId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, nickname: nickname || undefined, preferredLanguage }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => null)
        setError(data?.errors?.[0]?.message ?? 'Failed to save.')
      } else {
        setSuccess(true)
        router.refresh()
      }
    })
  }

  const initials = (name ?? email).charAt(0).toUpperCase()

  return (
    <form className="space-y-8" onSubmit={handleSubmit}>
      {/* Avatar */}
      <div className="flex items-center gap-5">
        <button
          type="button"
          className="relative group rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          onClick={() => fileRef.current?.click()}
          aria-label="Change profile photo"
          disabled={isUploading}
        >
          <span className="flex size-16 items-center justify-center overflow-hidden rounded-full bg-surface-secondary border border-border">
            {preview ? (
              <Image
                src={preview}
                alt="Avatar"
                width={64}
                height={64}
                className="size-16 rounded-full object-cover"
                unoptimized={preview.startsWith('blob:')}
              />
            ) : (
              <span className="text-xl font-semibold text-muted">{initials}</span>
            )}
          </span>
          <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
            <svg className="size-4 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points="17 8 12 3 7 8" strokeLinecap="round" strokeLinejoin="round" />
              <line x1="12" x2="12" y1="3" y2="15" strokeLinecap="round" />
            </svg>
          </span>
        </button>

        <div>
          <p className="text-sm font-medium text-foreground">Profile photo</p>
          <p className="mt-0.5 text-xs text-muted">JPG, PNG or GIF · max 5 MB</p>
          {avatarError && <p className="mt-1 text-xs text-danger">{avatarError}</p>}
          {isUploading && <p className="mt-1 text-xs text-muted">Uploading…</p>}
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="sr-only"
          onChange={handleAvatarChange}
        />
      </div>

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Fields */}
      <div className="space-y-5">
        {/* Email — read only */}
        <div>
          <label className="block text-[11px] font-semibold tracking-widest uppercase text-muted mb-1.5">
            Email
          </label>
          <input
            className="w-full rounded-xl border border-border bg-surface-secondary px-4 py-2.5 text-sm text-muted cursor-not-allowed"
            value={email}
            readOnly
            disabled
          />
        </div>

        {/* Name */}
        <div>
          <label className="block text-[11px] font-semibold tracking-widest uppercase text-muted mb-1.5" htmlFor="profile-name">
            Name
          </label>
          <input
            id="profile-name"
            name="name"
            type="text"
            defaultValue={name ?? ''}
            maxLength={80}
            placeholder="Your full name"
            className="w-full rounded-xl border border-border bg-field-background px-4 py-2.5 text-sm text-field-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-focus transition"
          />
        </div>

        {/* Nickname */}
        <div>
          <label className="block text-[11px] font-semibold tracking-widest uppercase text-muted mb-1.5" htmlFor="profile-nickname">
            Nickname
          </label>
          <input
            id="profile-nickname"
            name="nickname"
            type="text"
            defaultValue={nickname ?? ''}
            maxLength={40}
            placeholder="Optional display name"
            className="w-full rounded-xl border border-border bg-field-background px-4 py-2.5 text-sm text-field-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-focus transition"
          />
        </div>

        {/* Language */}
        <div>
          <label className="block text-[11px] font-semibold tracking-widest uppercase text-muted mb-1.5" htmlFor="profile-language">
            Language
          </label>
          <select
            id="profile-language"
            name="preferredLanguage"
            defaultValue={preferredLanguage ?? 'en'}
            className="w-full rounded-xl border border-border bg-field-background px-4 py-2.5 text-sm text-field-foreground focus:outline-none focus:ring-2 focus:ring-focus transition"
          >
            <option value="en">English</option>
            <option value="es">Español</option>
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}
      {success && <p className="text-sm text-success">Profile updated.</p>}

      <button
        type="submit"
        disabled={isPending}
        className="inline-flex h-10 items-center justify-center rounded-full bg-accent px-6 text-sm font-medium text-accent-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
      >
        {isPending ? 'Saving…' : 'Save changes'}
      </button>
    </form>
  )
}
