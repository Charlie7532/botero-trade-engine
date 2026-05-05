'use client'

import { useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'

type Props = {
  portfolioId: number | string
  currentName: string
}

export default function RenamePortfolioForm({ portfolioId, currentName }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [isPending, startTransition] = useTransition()
  const inputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = (inputRef.current?.value ?? '').trim()
    setError(null)
    setSuccess(false)

    if (!name) return setError('Name cannot be empty.')
    if (name.length > 80) return setError('Name must be 80 characters or fewer.')

    startTransition(async () => {
      const res = await fetch(`/api/portfolios/${portfolioId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
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

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <label
          className="block text-[11px] font-semibold tracking-widest uppercase text-muted mb-1.5"
          htmlFor="portfolio-name"
        >
          Portfolio Name
        </label>
        <input
          className="w-full rounded-xl border border-border bg-field-background px-4 py-2.5 text-sm text-field-foreground placeholder:text-field-placeholder focus:outline-none focus:ring-2 focus:ring-focus transition"
          defaultValue={currentName}
          id="portfolio-name"
          maxLength={80}
          name="name"
          placeholder="My Portfolio"
          ref={inputRef}
          type="text"
        />
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}
      {success && <p className="text-sm text-success">Name updated.</p>}

      <button
        className="inline-flex h-10 items-center justify-center rounded-full bg-accent px-6 text-sm font-medium text-accent-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
        disabled={isPending}
        type="submit"
      >
        {isPending ? 'Saving…' : 'Save'}
      </button>
    </form>
  )
}
