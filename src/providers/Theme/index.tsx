'use client'

import React, { createContext, use } from 'react'
import { ThemeProvider as NextThemesProvider, useTheme as useNextTheme } from 'next-themes'

import type { Theme, ThemeContextType, ThemeProviderProps, ThemeMode } from './types'

const initialContext: ThemeContextType = {
  setTheme: () => null,
  theme: undefined,
  resolvedTheme: undefined,
}

const ThemeContext = createContext(initialContext)

export const ThemeProvider = ({
  children,
  themeMode = 'both',
  defaultTheme = 'system'
}: ThemeProviderProps) => {
  // Determine forced theme based on themeMode
  const forcedTheme = themeMode === 'light-only' ? 'light' : themeMode === 'dark-only' ? 'dark' : undefined

  // Determine the effective default theme
  const effectiveDefault = themeMode === 'light-only' ? 'light'
    : themeMode === 'dark-only' ? 'dark'
      : defaultTheme

  return (
    <NextThemesProvider
      attribute="data-theme"
      defaultTheme={effectiveDefault}
      forcedTheme={forcedTheme}
      enableSystem={themeMode === 'both'}
      disableTransitionOnChange
    >
      <ThemeContextBridge themeMode={themeMode}>
        {children}
      </ThemeContextBridge>
    </NextThemesProvider>
  )
}

// Bridge component to provide our custom context from next-themes
const ThemeContextBridge = ({
  children,
  themeMode
}: {
  children: React.ReactNode
  themeMode: ThemeMode
}) => {
  const { theme, setTheme: setNextTheme, resolvedTheme } = useNextTheme()

  const setTheme = (themeToSet: Theme | null) => {
    if (themeMode !== 'both') return // Don't allow changes if forced
    if (themeToSet === null) {
      setNextTheme('system')
    } else {
      setNextTheme(themeToSet)
    }
  }

  return (
    <ThemeContext value={{
      setTheme,
      theme: (theme as Theme) || undefined,
      resolvedTheme: (resolvedTheme as Theme) || undefined,
    }}>
      {children}
    </ThemeContext>
  )
}

export const useTheme = (): ThemeContextType => use(ThemeContext)

// Re-export types for convenience
export type { Theme, ThemeMode, DefaultTheme, ThemeContextType, ThemeProviderProps } from './types'
export { themeIsValid } from './types'
