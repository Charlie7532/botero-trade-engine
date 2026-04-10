/**
 * Utility functions for generating dynamic CSS from site settings
 */

// Convert hex color to HSL
function hexToHsl(hex: string): { h: number; s: number; l: number } {
    // Remove the hash if present
    hex = hex.replace(/^#/, '')

    // Parse the hex values
    const r = parseInt(hex.substr(0, 2), 16) / 255
    const g = parseInt(hex.substr(2, 2), 16) / 255
    const b = parseInt(hex.substr(4, 2), 16) / 255

    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    let h = 0
    let s = 0
    const l = (max + min) / 2

    if (max === min) {
        h = s = 0 // achromatic
    } else {
        const d = max - min
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break
            case g: h = (b - r) / d + 2; break
            case b: h = (r - g) / d + 4; break
        }
        h /= 6
    }

    return {
        h: Math.round(h * 360),
        s: Math.round(s * 100),
        l: Math.round(l * 100)
    }
}

// Adjust lightness for theme variations
function adjustLightness(hsl: { h: number; s: number; l: number }, adjustment: number): string {
    const newL = Math.max(0, Math.min(100, hsl.l + adjustment))
    return `${hsl.h} ${hsl.s}% ${newL}%`
}

// Generate dynamic CSS variables based on site settings
export function generateDynamicCSS(siteSettings: any): string {
    if (!siteSettings?.themeSettings?.customColors) {
        return '' // Return empty string if custom colors are disabled
    }

    const { primaryColor = '#3E86B0', secondaryColor = '#6B7280' } = siteSettings.themeSettings

    // Convert colors to HSL
    const primaryHsl = hexToHsl(primaryColor)
    const secondaryHsl = hexToHsl(secondaryColor)

    // Generate light theme variations (slightly darker for better contrast)
    const primaryLight = adjustLightness(primaryHsl, -5)
    const primaryLightForeground = primaryHsl.l > 50 ? '0 0% 0%' : '0 0% 100%'

    const secondaryLight = adjustLightness(secondaryHsl, 0)
    const secondaryLightForeground = secondaryHsl.l > 50 ? '0 0% 0%' : '0 0% 100%'

    // Generate dark theme variations (slightly lighter for better contrast)
    const primaryDark = adjustLightness(primaryHsl, 10)
    const primaryDarkForeground = primaryHsl.l > 50 ? '0 0% 0%' : '0 0% 100%'

    const secondaryDark = adjustLightness(secondaryHsl, 15)
    const secondaryDarkForeground = secondaryHsl.l > 50 ? '0 0% 0%' : '0 0% 100%'

    return `
    :root {
      --primary: ${primaryLight};
      --primary-foreground: ${primaryLightForeground};
      --secondary: ${secondaryLight};
      --secondary-foreground: ${secondaryLightForeground};
    }

    [data-theme='dark'] {
      --primary: ${primaryDark};
      --primary-foreground: ${primaryDarkForeground};
      --secondary: ${secondaryDark};
      --secondary-foreground: ${secondaryDarkForeground};
    }
  `
}

// Check what theme modes are supported
export function getThemeConfig(siteSettings: any) {
    const themeMode = siteSettings?.themeSettings?.themeMode || 'both'
    const defaultTheme = siteSettings?.themeSettings?.defaultTheme || 'light'

    return {
        supportsBoth: themeMode === 'both',
        supportsLight: themeMode === 'light-only' || themeMode === 'both',
        supportsDark: themeMode === 'dark-only' || themeMode === 'both',
        defaultTheme: themeMode === 'light-only' ? 'light' :
            themeMode === 'dark-only' ? 'dark' :
                defaultTheme,
        themeMode
    }
}