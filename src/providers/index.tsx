import React from 'react'

import { HeaderThemeProvider } from './HeaderTheme'
import { ThemeProvider, type ThemeProviderProps } from './Theme'

export interface ProvidersProps extends Omit<ThemeProviderProps, 'children'> {
  children: React.ReactNode
}

export const Providers: React.FC<ProvidersProps> = ({
  children,
  themeMode,
  defaultTheme,
}) => {
  return (
    <ThemeProvider themeMode={themeMode} defaultTheme={defaultTheme}>
      <HeaderThemeProvider>{children}</HeaderThemeProvider>
    </ThemeProvider>
  )
}
