'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import mermaid from 'mermaid'
import { Icon } from '@iconify/react'

let mermaidInitialized = false

type Props = {
  chart: string
}

export function MermaidBlock({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    if (!mermaidInitialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',
      })
      mermaidInitialized = true
    }

    let cancelled = false
    const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`

    async function renderChart() {
      try {
        // Validate syntax first — this throws on invalid diagrams
        // without injecting error SVGs into the DOM
        await mermaid.parse(chart)

        const { svg: rendered } = await mermaid.render(id, chart)
        if (!cancelled) setSvg(rendered)
      } catch (err) {
        console.warn('[MermaidBlock] Failed to render diagram:', err)
        if (!cancelled) setError('parse-fail')
      } finally {
        // Clean up any orphaned container mermaid may have injected
        const orphan = document.getElementById('d' + id)
        orphan?.remove()
      }
    }

    renderChart()

    return () => {
      cancelled = true
    }
  }, [chart])

  // Close modal on Escape key
  useEffect(() => {
    if (!fullscreen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setFullscreen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [fullscreen])

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) setFullscreen(false)
  }, [])

  if (error) {
    return (
      <pre className="text-xs text-foreground-500 bg-content2 rounded-lg p-3 overflow-x-auto">
        <code>{chart}</code>
      </pre>
    )
  }

  if (!svg) return null

  return (
    <>
      {/* Inline chart with expand button */}
      <div className="group relative my-2 flex justify-center overflow-x-auto">
        <div
          ref={containerRef}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
        <button
          onClick={() => setFullscreen(true)}
          className="absolute top-1 right-1 p-1.5 rounded-lg bg-background/70 border border-divider/50 text-foreground-400 opacity-0 group-hover:opacity-100 hover:text-foreground hover:bg-background transition-all duration-200 cursor-pointer"
          aria-label="Expand diagram"
        >
          <Icon icon="lucide:maximize-2" className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Fullscreen modal */}
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={handleBackdropClick}
        >
          <div className="relative w-[90vw] h-[90vh] flex items-center justify-center bg-content1 border border-divider rounded-2xl shadow-2xl overflow-auto p-8">
            <button
              onClick={() => setFullscreen(false)}
              className="absolute top-3 right-3 p-2 rounded-xl bg-content2 border border-divider text-foreground-400 hover:text-foreground hover:bg-content3 transition-colors cursor-pointer z-10"
              aria-label="Close fullscreen"
            >
              <Icon icon="lucide:x" className="w-4 h-4" />
            </button>
            <div
              className="max-w-full max-h-full [&_svg]:max-w-full [&_svg]:max-h-[80vh] [&_svg]:w-auto [&_svg]:h-auto"
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          </div>
        </div>
      )}
    </>
  )
}
