'use client'

import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

let mermaidInitialized = false

type Props = {
  chart: string
}

export function MermaidBlock({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!mermaidInitialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',
      })
      mermaidInitialized = true
    }

    const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`

    mermaid
      .render(id, chart)
      .then(({ svg: rendered }) => setSvg(rendered))
      .catch(() => setError('Failed to render diagram'))
  }, [chart])

  if (error) {
    return (
      <pre className="text-xs text-danger bg-danger/10 rounded-lg p-3 overflow-x-auto">
        {chart}
      </pre>
    )
  }

  return (
    <div
      ref={containerRef}
      className="my-2 flex justify-center overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
