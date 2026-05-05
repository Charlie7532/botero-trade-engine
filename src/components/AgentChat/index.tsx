'use client'

import { useState, useRef, useEffect, type FormEvent } from 'react'
import { Button, Chip, Spinner } from '@heroui/react'
import { Icon } from '@iconify/react'
import { IconThemeSwitch } from '@/components/ui/IconThemeSwitch'
import { MarkdownRenderer } from './MarkdownRenderer'

type Message = {
  content: string
  role: 'user' | 'assistant'
}

type Props = {
  botSlug: string
  botName: string
  botDescription: string
  modelName: string
}

export function AgentChat({ botSlug, botName, botDescription, modelName }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMessage: Message = { role: 'user', content: input.trim() }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInput('')
    setLoading(true)
    setError('')

    try {
      const res = await fetch(`/api/agent/${botSlug}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error || `Error ${res.status}`)
      }

      const data = await res.json()
      const assistantText =
        data.content
          ?.filter((b: any) => b.type === 'text')
          .map((b: any) => b.text)
          .join('') || 'No response'

      setMessages([...newMessages, { role: 'assistant', content: assistantText }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as FormEvent)
    }
  }

  return (
    <div className="flex flex-col h-screen w-full">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-divider backdrop-blur-md bg-background/80 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
          <div>
            <h1 className="text-base font-semibold text-foreground">{botName}</h1>
            {botDescription && (
              <p className="text-xs text-foreground-400 line-clamp-1">{botDescription}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Chip size="sm" variant="flat" className="font-mono text-[11px]">
            {modelName}
          </Chip>
          <IconThemeSwitch />
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-5 py-5 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center flex-1 gap-3 opacity-40">
            <Icon icon="lucide:message-square" className="w-10 h-10 text-foreground-300" />
            <p className="text-sm text-foreground-500">
              Start a conversation with <strong>{botName}</strong>
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'self-end bg-primary text-primary-foreground rounded-br-sm'
                : 'self-start bg-content2 text-foreground rounded-bl-sm'
            }`}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <Icon
                icon={msg.role === 'user' ? 'lucide:user' : 'lucide:bot'}
                className="w-3 h-3 opacity-50"
              />
              <span className="text-[11px] font-semibold uppercase tracking-wider opacity-50">
                {msg.role === 'user' ? 'You' : botName}
              </span>
            </div>
            {msg.role === 'user' ? (
              <div className="whitespace-pre-wrap break-words">{msg.content}</div>
            ) : (
              <MarkdownRenderer content={msg.content} />
            )}
          </div>
        ))}

        {loading && (
          <div className="self-start bg-content2 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-2">
            <Spinner size="sm" />
            <span className="text-xs text-foreground-400">Thinking...</span>
          </div>
        )}

        {error && (
          <div className="self-center flex items-center gap-2 px-4 py-2 bg-danger/10 border border-danger/30 rounded-lg text-danger text-xs">
            <Icon icon="lucide:alert-triangle" className="w-3.5 h-3.5" />
            {error}
          </div>
        )}

        <div ref={endRef} />
      </main>

      {/* Input */}
      <footer className="px-5 pb-5 pt-3 border-t border-divider bg-background/80 backdrop-blur-md">
        <form onSubmit={handleSubmit} className="flex items-end gap-2 w-full">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${botName}...`}
            disabled={loading}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-divider bg-content1 px-4 py-3 text-sm text-foreground placeholder:text-foreground-400 outline-none focus:border-primary transition-colors"
          />
          <Button
            type="submit"
            isDisabled={loading || !input.trim()}
            isIconOnly
            color="primary"
            size="lg"
            radius="lg"
          >
            <Icon icon="lucide:arrow-up" className="w-5 h-5" />
          </Button>
        </form>
      </footer>
    </div>
  )
}
