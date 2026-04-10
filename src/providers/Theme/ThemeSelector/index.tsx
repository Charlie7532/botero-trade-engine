'use client'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import React from 'react'
import { useTheme } from '@/providers/Theme'

import type { Theme } from './types'

export const ThemeSelector: React.FC = () => {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  // Avoid hydration mismatch
  React.useEffect(() => {
    setMounted(true)
  }, [])

  const onThemeChange = (themeToSet: Theme | 'system') => {
    // Our provider uses null to mean 'system'
    if (themeToSet === 'system') {
      setTheme(null)
    } else {
      setTheme(themeToSet)
    }
  }

  if (!mounted) {
    return (
      <Select disabled>
        <SelectTrigger
          aria-label="Select a theme"
          className="w-auto bg-transparent gap-2 pl-0 md:pl-3 border-none"
        >
          <SelectValue placeholder="Theme" />
        </SelectTrigger>
      </Select>
    )
  }

  // Determine current value for the select
  // If theme is null/undefined and we have a resolved theme, it means 'system' is active  
  const currentValue = theme || 'system'

  return (
    <Select onValueChange={onThemeChange} value={currentValue}>
      <SelectTrigger
        aria-label="Select a theme"
        className="w-auto bg-transparent gap-2 pl-0 md:pl-3 border-none"
        data-theme-switch
      >
        <SelectValue placeholder="Theme" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="system">System</SelectItem>
        <SelectItem value="light">Light</SelectItem>
        <SelectItem value="dark">Dark</SelectItem>
      </SelectContent>
    </Select>
  )
}
