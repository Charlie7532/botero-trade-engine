'use client'

import React, { useEffect, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Modal, Button } from '@heroui/react'
import { Briefcase, AlertCircle } from 'lucide-react'

import { createPortfolio } from '@/app/(frontend)/portafolio/actions'

type Props = {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

const inputCls =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-foreground/40 focus:ring-2 focus:ring-foreground/10 placeholder:text-muted'
const labelCls = 'block text-xs font-medium text-foreground'
const helpCls = 'mt-1 text-xs text-muted'

const NewPortafolioDialog: React.FC<Props> = ({ isOpen, onOpenChange }) => {
  const router = useRouter()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    if (!isOpen) {
      // Defer reset until after the close animation.
      const t = setTimeout(() => {
        setName('')
        setError(null)
      }, 200)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  const canSubmit = name.trim().length > 0 && !isPending

  const handleSubmit = () => {
    setError(null)
    startTransition(async () => {
      const result = await createPortfolio({ name })
      if (!result.ok) {
        setError(result.error)
        return
      }
      onOpenChange(false)
      router.push(`/portafolio/${result.slug}`)
      router.refresh()
    })
  }

  return (
    <Modal.Backdrop isOpen={isOpen} onOpenChange={onOpenChange}>
      <Modal.Container>
        <Modal.Dialog className="sm:max-w-[460px]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Icon className="bg-default text-foreground">
              <Briefcase className="size-5" />
            </Modal.Icon>
            <Modal.Heading>Create a new portfolio</Modal.Heading>
            <p className="mt-1 text-xs text-muted">
              You will be the owner. A unique ID is generated automatically.
            </p>
          </Modal.Header>

          <Modal.Body>
            <div className="flex flex-col gap-4">
              <div>
                <label className={labelCls} htmlFor="np-name">
                  Portfolio name
                </label>
                <input
                  id="np-name"
                  type="text"
                  className={`mt-1.5 ${inputCls}`}
                  placeholder="e.g. Long-Term Quality"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={80}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && canSubmit) {
                      e.preventDefault()
                      handleSubmit()
                    }
                  }}
                />
                <p className={helpCls}>Up to 80 characters.</p>
              </div>

              {error ? (
                <p className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  <AlertCircle size={14} className="mt-0.5 shrink-0" />
                  {error}
                </p>
              ) : null}
            </div>
          </Modal.Body>

          <Modal.Footer>
            <Button slot="close" variant="secondary" isDisabled={isPending}>
              Cancel
            </Button>
            <Button onPress={handleSubmit} isDisabled={!canSubmit}>
              {isPending ? 'Creating…' : 'Create portfolio'}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  )
}

export default NewPortafolioDialog
