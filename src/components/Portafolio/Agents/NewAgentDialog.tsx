'use client'

import React, { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Modal, Button } from '@heroui/react'
import { Plus, Bot, AlertCircle } from 'lucide-react'

import { createBot, type CreateBotInput } from '@/app/(frontend)/portafolio/[slug]/agents/actions'

type Props = {
  portfolioSlug: string
  triggerLabel?: string
}

type ExecutionType = 'agent' | 'strategy'
type StrategyType = CreateBotInput['strategyType']
type ClaudeModel = NonNullable<CreateBotInput['model']>

type FormState = {
  name: string
  description: string
  executionType: ExecutionType
  strategyType: StrategyType
  model: ClaudeModel
  systemPrompt: string
}

const INITIAL_STATE: FormState = {
  name: '',
  description: '',
  executionType: 'agent',
  strategyType: 'custom',
  model: 'claude-sonnet-4-6',
  systemPrompt: '',
}

const EXECUTION_OPTIONS: { value: ExecutionType; label: string; description: string }[] = [
  {
    value: 'agent',
    label: 'AI Agent (Claude)',
    description: 'LLM-powered agent with system prompt, MCP tools, and skills.',
  },
  {
    value: 'strategy',
    label: 'Strategy (Backend)',
    description: 'Deterministic algorithm executed by the Python engine.',
  },
]

const QUALITY_STRATEGIES: { value: StrategyType; label: string }[] = [
  { value: 'quality_value', label: 'Quality · Value' },
  { value: 'quality_growth', label: 'Quality · Growth' },
  { value: 'quality_dividend', label: 'Quality · Dividend' },
]

const SPECULATIVE_STRATEGIES: { value: StrategyType; label: string }[] = [
  { value: 'speculative_momentum', label: 'Speculative · Momentum' },
  { value: 'speculative_gamma', label: 'Speculative · Gamma' },
  { value: 'speculative_breakout', label: 'Speculative · Breakout' },
  { value: 'speculative_spring', label: 'Speculative · Spring' },
]

const MODEL_OPTIONS: { value: ClaudeModel; label: string }[] = [
  { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
  { value: 'claude-haiku-4', label: 'Claude Haiku 4' },
]

const inputCls =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-foreground/40 focus:ring-2 focus:ring-foreground/10 placeholder:text-muted'
const labelCls = 'block text-xs font-medium text-foreground'
const helpCls = 'mt-1 text-xs text-muted'

const NewAgentDialog: React.FC<Props> = ({ portfolioSlug, triggerLabel = 'New Agent' }) => {
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
    if (!open) setTimeout(reset, 200)
  }

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const canSubmit = form.name.trim().length > 0

  const handleSubmit = () => {
    setError(null)
    const payload: CreateBotInput = {
      portfolioSlug,
      name: form.name,
      executionType: form.executionType,
      strategyType: form.strategyType,
    }
    if (form.description.trim()) payload.description = form.description
    if (form.executionType === 'agent') {
      payload.model = form.model
      if (form.systemPrompt.trim()) payload.systemPrompt = form.systemPrompt
    }

    startTransition(async () => {
      const result = await createBot(payload)
      if (!result.ok) {
        setError(result.error)
        return
      }
      handleOpenChange(false)
      if (form.executionType === 'agent' && result.botSlug) {
        router.push(`/agent/${result.botSlug}`)
      } else {
        router.refresh()
      }
    })
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-secondary transition-colors"
      >
        <Plus size={14} />
        {triggerLabel}
      </button>

      <Modal.Backdrop isOpen={isOpen} onOpenChange={handleOpenChange}>
        <Modal.Container>
          <Modal.Dialog className="sm:max-w-[560px]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Icon className="bg-default text-foreground">
                <Bot className="size-5" />
              </Modal.Icon>
              <Modal.Heading>Create an agent</Modal.Heading>
              <p className="mt-1 text-xs text-muted">
                Step {step} of 2 ·{' '}
                {step === 1 ? 'Choose execution type' : 'Configure agent'}
              </p>
            </Modal.Header>

            <Modal.Body>
              {step === 1 ? (
                <div className="flex flex-col gap-5">
                  <div>
                    <label className={labelCls} htmlFor="ag-name">
                      Name
                    </label>
                    <input
                      id="ag-name"
                      type="text"
                      className={`mt-1.5 ${inputCls}`}
                      placeholder="e.g. Quality Scanner · Hohn Mode"
                      value={form.name}
                      onChange={(e) => update('name', e.target.value)}
                      maxLength={80}
                    />
                  </div>

                  <div>
                    <p className={labelCls}>Execution type</p>
                    <div className="mt-1.5 grid gap-2">
                      {EXECUTION_OPTIONS.map((opt) => {
                        const selected = form.executionType === opt.value
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => update('executionType', opt.value)}
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
                                {opt.label}
                              </span>
                              <span className="mt-0.5 block text-xs text-muted">
                                {opt.description}
                              </span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div>
                    <label className={labelCls} htmlFor="ag-strategy">
                      Strategy bucket
                    </label>
                    <select
                      id="ag-strategy"
                      className={`mt-1.5 ${inputCls}`}
                      value={form.strategyType}
                      onChange={(e) => update('strategyType', e.target.value as StrategyType)}
                    >
                      <optgroup label="Quality (80%)">
                        {QUALITY_STRATEGIES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </optgroup>
                      <optgroup label="Speculative (20%)">
                        {SPECULATIVE_STRATEGIES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </optgroup>
                      <optgroup label="Other">
                        <option value="custom">Custom</option>
                      </optgroup>
                    </select>
                    <p className={helpCls}>Determines department routing and risk policy.</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-5">
                  {form.executionType === 'agent' ? (
                    <>
                      <div>
                        <label className={labelCls} htmlFor="ag-model">
                          Claude model
                        </label>
                        <select
                          id="ag-model"
                          className={`mt-1.5 ${inputCls}`}
                          value={form.model}
                          onChange={(e) => update('model', e.target.value as ClaudeModel)}
                        >
                          {MODEL_OPTIONS.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className={labelCls} htmlFor="ag-prompt">
                          System prompt <span className="text-muted">(optional)</span>
                        </label>
                        <textarea
                          id="ag-prompt"
                          rows={6}
                          className={`mt-1.5 font-mono text-xs ${inputCls}`}
                          placeholder="You are a research analyst specialized in ..."
                          value={form.systemPrompt}
                          onChange={(e) => update('systemPrompt', e.target.value)}
                        />
                        <p className={helpCls}>
                          Defines the agent's persona and expertise. You can add MCP servers and
                          skills later from the agent page.
                        </p>
                      </div>
                    </>
                  ) : (
                    <p className="rounded-lg border border-border bg-surface-secondary px-3 py-2 text-xs text-muted">
                      Strategy bots are configured by the Python backend. After creation you can
                      attach broker accounts and tune parameters from the bot page.
                    </p>
                  )}

                  <div>
                    <label className={labelCls} htmlFor="ag-desc">
                      Description <span className="text-muted">(optional)</span>
                    </label>
                    <textarea
                      id="ag-desc"
                      rows={3}
                      className={`mt-1.5 ${inputCls}`}
                      placeholder="Short summary shown on the agents list."
                      value={form.description}
                      onChange={(e) => update('description', e.target.value)}
                    />
                  </div>

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
                  <Button onPress={() => setStep(2)} isDisabled={!canSubmit}>
                    Next
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="secondary" onPress={() => setStep(1)} isDisabled={isPending}>
                    Back
                  </Button>
                  <Button onPress={handleSubmit} isDisabled={!canSubmit || isPending}>
                    {isPending ? 'Creating…' : 'Create agent'}
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

export default NewAgentDialog
