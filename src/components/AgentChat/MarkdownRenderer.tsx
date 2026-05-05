'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MermaidBlock } from './MermaidBlock'

type Props = {
  content: string
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Headings
        h1: ({ children }) => (
          <h1 className="text-xl font-bold mt-4 mb-2 text-foreground">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-lg font-semibold mt-3 mb-1.5 text-foreground">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-base font-semibold mt-2 mb-1 text-foreground">{children}</h3>
        ),
        h4: ({ children }) => (
          <h4 className="text-sm font-semibold mt-2 mb-1 text-foreground">{children}</h4>
        ),

        // Paragraphs
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,

        // Lists
        ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,

        // Bold & italic
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,

        // Inline code
        code: ({ className, children, ...props }) => {
          const match = /language-(\w+)/.exec(className || '')
          const language = match?.[1]

          // Mermaid code blocks
          if (language === 'mermaid') {
            return <MermaidBlock chart={String(children).trim()} />
          }

          // Block code
          if (className) {
            return (
              <pre className="bg-content1 border border-divider rounded-lg p-3 my-2 overflow-x-auto">
                <code className="text-xs font-mono leading-relaxed" {...props}>
                  {children}
                </code>
              </pre>
            )
          }

          // Inline code
          return (
            <code
              className="bg-content1 border border-divider text-xs font-mono px-1.5 py-0.5 rounded"
              {...props}
            >
              {children}
            </code>
          )
        },

        // Pre blocks (wrapping code)
        pre: ({ children }) => <>{children}</>,

        // Blockquote
        blockquote: ({ children }) => (
          <blockquote className="border-l-3 border-primary/50 pl-3 my-2 text-foreground-500 italic">
            {children}
          </blockquote>
        ),

        // Horizontal rule
        hr: () => <hr className="border-divider my-3" />,

        // Links
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:text-primary/80 transition-colors"
          >
            {children}
          </a>
        ),

        // Tables
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="w-full text-xs border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-content1 border-b border-divider">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left font-semibold text-foreground-500">{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 border-b border-divider/50">{children}</td>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
