'use client'

import React, { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Modal, Button } from '@heroui/react'
import { Plus, Plug, AlertCircle, CheckCircle2 } from 'lucide-react'

import { Textarea } from '@/components/ui/textarea'

import {
  createBrokerAccount,
  type CreateBrokerAccountInput,
} from '@/app/(frontend)/portafolio/[slug]/brokers/actions'

type Props = {
  portfolioSlug: string
  triggerLabel?: string
  triggerVariant?: 'primary' | 'subtle'
}

type BrokerType = 'alpaca' | 'interactive_brokers'
type Environment = 'paper' | 'live'
type Department = 'quality' | 'speculative' | 'mixed'

type FormState = {
  name: string
  brokerType: BrokerType
  environment: Environment
  department: Department
  apiKeyPlaintext: string
  secretKeyPlaintext: string
  alpacaBaseUrl: string
  ibAccountId: string
  ibConsumerKeyPlaintext: string
  ibAccessTokenPlaintext: string
  ibAccessTokenSecretPlaintext: string
  ibDhPrime: string
  ibSignatureKeyPemPlaintext: string
  ibEncryptionKeyPemPlaintext: string
}

const INITIAL_STATE: FormState = {
  name: '',
  brokerType: 'alpaca',
  environment: 'paper',
  department: 'quality',
  apiKeyPlaintext: '',
  secretKeyPlaintext: '',
  alpacaBaseUrl: '',
  ibAccountId: '',
  ibConsumerKeyPlaintext: '',
  ibAccessTokenPlaintext: '',
  ibAccessTokenSecretPlaintext: '',
  ibDhPrime: '',
  ibSignatureKeyPemPlaintext: '',
  ibEncryptionKeyPemPlaintext: '',
}

const BROKERS: { value: BrokerType; label: string; description: string }[] = [
  {
    value: 'alpaca',
    label: 'Alpaca',
    description: 'REST API. Paper or live trading. US equities and crypto.',
  },
  {
    value: 'interactive_brokers',
    label: 'Interactive Brokers',
    description: 'OAuth (Web API). Global multi-asset coverage, no local Gateway needed.',
  },
]

const inputCls =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-foreground/40 focus:ring-2 focus:ring-foreground/10 placeholder:text-muted'

const labelCls = 'block text-xs font-medium text-foreground'
const helpCls = 'mt-1 text-xs text-muted'

const NewBrokerAccountDialog: React.FC<Props> = ({
  portfolioSlug,
  triggerLabel = 'New Account',
  triggerVariant = 'primary',
}) => {
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(false)
  const [step, setStep] = useState<1 | 2>(1)
  const [form, setForm] = useState<FormState>(INITIAL_STATE)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const reset = () => {
    setStep(1)
    setForm(INITIAL_STATE)
    setError(null)
  }

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    if (!open) {
      // Defer to allow exit animation before clearing fields.
      setTimeout(reset, 200)
    }
  }

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const canSubmit = (() => {
    if (!form.name.trim()) return false
    if (form.brokerType === 'alpaca') {
      return form.apiKeyPlaintext.trim().length > 0 && form.secretKeyPlaintext.trim().length > 0
    }
    return (
      form.ibAccountId.trim().length > 0 &&
      form.ibConsumerKeyPlaintext.trim().length > 0 &&
      form.ibAccessTokenPlaintext.trim().length > 0 &&
      form.ibAccessTokenSecretPlaintext.trim().length > 0 &&
      form.ibDhPrime.trim().length > 0 &&
      form.ibSignatureKeyPemPlaintext.trim().length > 0 &&
      form.ibEncryptionKeyPemPlaintext.trim().length > 0
    )
  })()

  const handleSubmit = () => {
    setError(null)
    const payload: CreateBrokerAccountInput = {
      portfolioSlug,
      name: form.name,
      brokerType: form.brokerType,
      environment: form.environment,
      department: form.department,
    }
    if (form.brokerType === 'alpaca') {
      payload.apiKeyPlaintext = form.apiKeyPlaintext
      payload.secretKeyPlaintext = form.secretKeyPlaintext
      if (form.alpacaBaseUrl.trim()) payload.alpacaBaseUrl = form.alpacaBaseUrl
    } else {
      payload.ibAccountId = form.ibAccountId
      payload.ibConsumerKeyPlaintext = form.ibConsumerKeyPlaintext
      payload.ibAccessTokenPlaintext = form.ibAccessTokenPlaintext
      payload.ibAccessTokenSecretPlaintext = form.ibAccessTokenSecretPlaintext
      payload.ibDhPrime = form.ibDhPrime
      payload.ibSignatureKeyPemPlaintext = form.ibSignatureKeyPemPlaintext
      payload.ibEncryptionKeyPemPlaintext = form.ibEncryptionKeyPemPlaintext
    }

    startTransition(async () => {
      const result = await createBrokerAccount(payload)
      if (!result.ok) {
        setError(result.error)
        return
      }
      handleOpenChange(false)
      router.refresh()
    })
  }

  const triggerCls =
    triggerVariant === 'primary'
      ? 'inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-secondary transition-colors'
      : 'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-foreground hover:bg-surface-secondary transition-colors'

  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)} className={triggerCls}>
        <Plus size={14} />
        {triggerLabel}
      </button>

      <Modal.Backdrop isOpen={isOpen} onOpenChange={handleOpenChange}>
        <Modal.Container>
          <Modal.Dialog className="sm:max-w-[520px]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Icon className="bg-default text-foreground">
                <Plug className="size-5" />
              </Modal.Icon>
              <Modal.Heading>Connect a broker account</Modal.Heading>
              <p className="mt-1 text-xs text-muted">
                Step {step} of 2 ·{' '}
                {step === 1 ? 'Choose broker and environment' : 'Enter credentials'}
              </p>
            </Modal.Header>

            <Modal.Body>
              {step === 1 ? (
                <div className="flex flex-col gap-5">
                  <div>
                    <label className={labelCls} htmlFor="ba-name">
                      Account name
                    </label>
                    <input
                      id="ba-name"
                      type="text"
                      className={`mt-1.5 ${inputCls}`}
                      placeholder="e.g. Alpaca Paper · Quality"
                      value={form.name}
                      onChange={(e) => update('name', e.target.value)}
                      maxLength={80}
                    />
                  </div>

                  <div>
                    <p className={labelCls}>Broker</p>
                    <div className="mt-1.5 grid gap-2">
                      {BROKERS.map((b) => {
                        const selected = form.brokerType === b.value
                        return (
                          <button
                            key={b.value}
                            type="button"
                            onClick={() => update('brokerType', b.value)}
                            className={[
                              'flex items-start gap-3 rounded-lg border px-3 py-3 text-left transition-colors',
                              selected
                                ? 'border-foreground/40 bg-surface-secondary'
                                : 'border-border bg-surface hover:bg-surface-secondary',
                            ].join(' ')}
                          >
                            <span
                              className={[
                                'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border',
                                selected ? 'border-foreground bg-foreground' : 'border-border',
                              ].join(' ')}
                            >
                              {selected ? (
                                <span className="size-1.5 rounded-full bg-surface" />
                              ) : null}
                            </span>
                            <span className="min-w-0">
                              <span className="block text-sm font-medium text-foreground">
                                {b.label}
                              </span>
                              <span className="mt-0.5 block text-xs text-muted">
                                {b.description}
                              </span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className={labelCls} htmlFor="ba-env">
                        Environment
                      </label>
                      <select
                        id="ba-env"
                        className={`mt-1.5 ${inputCls}`}
                        value={form.environment}
                        onChange={(e) => update('environment', e.target.value as Environment)}
                      >
                        <option value="paper">Paper</option>
                        <option value="live">Live</option>
                      </select>
                      <p className={helpCls}>
                        Paper trading is recommended until credentials are validated.
                      </p>
                    </div>

                    <div>
                      <label className={labelCls} htmlFor="ba-dept">
                        Department
                      </label>
                      <select
                        id="ba-dept"
                        className={`mt-1.5 ${inputCls}`}
                        value={form.department}
                        onChange={(e) => update('department', e.target.value as Department)}
                      >
                        <option value="quality">Quality</option>
                        <option value="speculative">Speculative</option>
                        <option value="mixed">Mixed</option>
                      </select>
                      <p className={helpCls}>Strategy bucket this account will serve.</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-5">
                  {form.brokerType === 'alpaca' ? (
                    <>
                      <div>
                        <label className={labelCls} htmlFor="ba-api-key">
                          API Key
                        </label>
                        <input
                          id="ba-api-key"
                          type="text"
                          autoComplete="off"
                          spellCheck={false}
                          className={`mt-1.5 font-mono ${inputCls}`}
                          placeholder="PKxxxxxxxxxxxxxxxxxx"
                          value={form.apiKeyPlaintext}
                          onChange={(e) => update('apiKeyPlaintext', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ba-secret-key">
                          Secret Key
                        </label>
                        <input
                          id="ba-secret-key"
                          type="password"
                          autoComplete="new-password"
                          spellCheck={false}
                          className={`mt-1.5 font-mono ${inputCls}`}
                          placeholder="••••••••••••••••••••••••••••••••"
                          value={form.secretKeyPlaintext}
                          onChange={(e) => update('secretKeyPlaintext', e.target.value)}
                        />
                        <p className={helpCls}>
                          Stored encrypted at rest. Only the last 4 characters are kept readable.
                        </p>
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ba-base-url">
                          Base URL <span className="text-muted">(optional)</span>
                        </label>
                        <input
                          id="ba-base-url"
                          type="text"
                          className={`mt-1.5 ${inputCls}`}
                          placeholder={
                            form.environment === 'paper'
                              ? 'https://paper-api.alpaca.markets'
                              : 'https://api.alpaca.markets'
                          }
                          value={form.alpacaBaseUrl}
                          onChange={(e) => update('alpacaBaseUrl', e.target.value)}
                        />
                        <p className={helpCls}>
                          Defaults to the {form.environment} URL when left blank.
                        </p>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <label className={labelCls} htmlFor="ba-ib-id">
                          IB Account ID
                        </label>
                        <input
                          id="ba-ib-id"
                          type="text"
                          autoComplete="off"
                          spellCheck={false}
                          className={`mt-1.5 font-mono ${inputCls}`}
                          placeholder="DU1234567"
                          value={form.ibAccountId}
                          onChange={(e) => update('ibAccountId', e.target.value)}
                        />
                      </div>
                      <div className="grid gap-4 sm:grid-cols-3">
                        <div>
                          <label className={labelCls} htmlFor="ba-ib-consumer-key">
                            Consumer Key
                          </label>
                          <input
                            id="ba-ib-consumer-key"
                            type="text"
                            autoComplete="off"
                            spellCheck={false}
                            className={`mt-1.5 font-mono ${inputCls}`}
                            placeholder="9 characters"
                            value={form.ibConsumerKeyPlaintext}
                            onChange={(e) => update('ibConsumerKeyPlaintext', e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={labelCls} htmlFor="ba-ib-access-token">
                            Access Token
                          </label>
                          <input
                            id="ba-ib-access-token"
                            type="text"
                            autoComplete="off"
                            spellCheck={false}
                            className={`mt-1.5 font-mono ${inputCls}`}
                            value={form.ibAccessTokenPlaintext}
                            onChange={(e) => update('ibAccessTokenPlaintext', e.target.value)}
                          />
                        </div>
                        <div>
                          <label className={labelCls} htmlFor="ba-ib-access-token-secret">
                            Access Token Secret
                          </label>
                          <input
                            id="ba-ib-access-token-secret"
                            type="password"
                            autoComplete="off"
                            spellCheck={false}
                            className={`mt-1.5 font-mono ${inputCls}`}
                            value={form.ibAccessTokenSecretPlaintext}
                            onChange={(e) => update('ibAccessTokenSecretPlaintext', e.target.value)}
                          />
                        </div>
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ba-ib-dh-prime">
                          Diffie-Hellman Prime (hex)
                        </label>
                        <Textarea
                          id="ba-ib-dh-prime"
                          rows={2}
                          spellCheck={false}
                          className="mt-1.5 font-mono text-xs"
                          placeholder="From: openssl dhparam -in dhparam.pem -text -noout"
                          value={form.ibDhPrime}
                          onChange={(e) => update('ibDhPrime', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ba-ib-sig-key">
                          RSA Signature Private Key (PEM)
                        </label>
                        <Textarea
                          id="ba-ib-sig-key"
                          rows={4}
                          spellCheck={false}
                          className="mt-1.5 font-mono text-xs"
                          placeholder="-----BEGIN RSA PRIVATE KEY-----"
                          value={form.ibSignatureKeyPemPlaintext}
                          onChange={(e) => update('ibSignatureKeyPemPlaintext', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ba-ib-enc-key">
                          RSA Encryption Private Key (PEM)
                        </label>
                        <Textarea
                          id="ba-ib-enc-key"
                          rows={4}
                          spellCheck={false}
                          className="mt-1.5 font-mono text-xs"
                          placeholder="-----BEGIN RSA PRIVATE KEY-----"
                          value={form.ibEncryptionKeyPemPlaintext}
                          onChange={(e) => update('ibEncryptionKeyPemPlaintext', e.target.value)}
                        />
                      </div>
                      <p className="flex items-start gap-2 rounded-lg border border-border bg-surface-secondary px-3 py-2 text-xs text-muted">
                        <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                        Generated once per IB account via IB&rsquo;s OAuth self-service portal — not a
                        local TWS/Gateway connection. Activation can take up to a few days.
                      </p>
                    </>
                  )}

                  {error ? (
                    <p className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                      <AlertCircle size={14} className="mt-0.5 shrink-0" />
                      {error}
                    </p>
                  ) : null}
                </div>
              )}
            </Modal.Body>

            <Modal.Footer>
              {step === 1 ? (
                <>
                  <Button slot="close" variant="secondary">
                    Cancel
                  </Button>
                  <Button onPress={() => setStep(2)} isDisabled={!form.name.trim()}>
                    Next
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="secondary" onPress={() => setStep(1)} isDisabled={isPending}>
                    Back
                  </Button>
                  <Button
                    onPress={handleSubmit}
                    isDisabled={!canSubmit || isPending}
                  >
                    {isPending ? 'Connecting…' : 'Connect account'}
                  </Button>
                </>
              )}
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  )
}

export default NewBrokerAccountDialog
