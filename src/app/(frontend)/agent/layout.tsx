import React from 'react'

/**
 * Minimal layout for agent chat pages.
 * No sidebar, no nav — just the chat component filling the viewport.
 * Works cleanly in both standalone view and Payload admin preview iframe.
 */
export default function AgentLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
