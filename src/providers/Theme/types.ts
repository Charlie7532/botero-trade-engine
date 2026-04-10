export type Theme = 'dark' | 'light'

/** Theme mode determines if users can switch themes or if one is forced */
export type ThemeMode = 'light-only' | 'dark-only' | 'both'

/** Default theme option - includes 'system' for auto detection */
export type DefaultTheme = 'light' | 'dark' | 'system'

export interface ThemeContextType {
  setTheme: (theme: Theme | null) => void
  theme?: Theme | null
  /** The actual resolved theme (accounts for 'system' setting) */
  resolvedTheme?: Theme
}

export interface ThemeProviderProps {
  children: React.ReactNode
  /** Controls whether theme switching is allowed */
  themeMode?: ThemeMode
  /** Default theme when themeMode is 'both' */
  defaultTheme?: DefaultTheme
}

export function themeIsValid(string: null | string): string is Theme {
  return string ? ['dark', 'light'].includes(string) : false
}
