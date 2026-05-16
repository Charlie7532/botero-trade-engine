'use client'

import React from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'
import { Tabs } from '@heroui/react'

import { useTheme } from '@/providers/Theme'
import type { Theme } from './types'

type ThemeId = Theme | 'system'

type Option = { id: ThemeId; label: string; Icon: typeof Sun }

const OPTIONS: Option[] = [
  { id: 'light', label: 'Light', Icon: Sun },
  { id: 'dark', label: 'Dark', Icon: Moon },
  { id: 'system', label: 'System', Icon: Monitor },
]

export type ThemeToggleGroupProps = {
  /** Show a label above the toggle group. */
  label?: string
  /** Hide the System option for deterministic light/dark only. */
  showSystem?: boolean
  className?: string
}

export const ThemeToggleGroup: React.FC<ThemeToggleGroupProps> = ({
  label,
  showSystem = true,
  className,
}) => {
  const { theme, setTheme } = useTheme()
  const active: ThemeId = theme === 'light' || theme === 'dark' ? theme : 'system'
  const options = showSystem ? OPTIONS : OPTIONS.filter((o) => o.id !== 'system')

  return (
    <div
      className={`flex w-full flex-col gap-1.5 ${className ?? ''}`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {label ? <span className="text-xs text-muted">{label}</span> : null}
      <Tabs
        className="w-full text-center"
        selectedKey={active}
        onSelectionChange={(key) => {
          const next = String(key) as ThemeId
          setTheme(next === 'system' ? null : next)
        }}
      >
        <Tabs.ListContainer>
          <Tabs.List
            aria-label="Theme"
            className="w-full *:flex-1 *:data-[selected=true]:text-accent-foreground"
          >
            {options.map(({ id, label: optLabel, Icon }) => (
              <Tabs.Tab key={id} id={id} aria-label={optLabel}>
                <Icon size={14} />
                <Tabs.Indicator className="bg-accent" />
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs.ListContainer>
      </Tabs>
    </div>
  )
}

export default ThemeToggleGroup
