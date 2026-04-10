/**
 * Utility function to convert hex color to HSL values
 * This is needed because Tailwind CSS uses HSL format for its color variables
 */
function hexToHsl(hex: string): string {
    // Remove the hash if present
    hex = hex.replace('#', '')

    // Parse r, g, b values
    const r = parseInt(hex.substring(0, 2), 16) / 255
    const g = parseInt(hex.substring(2, 4), 16) / 255
    const b = parseInt(hex.substring(4, 6), 16) / 255

    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    let h = 0
    let s = 0
    const l = (max + min) / 2

    if (max !== min) {
        const d = max - min
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break
            case g: h = (b - r) / d + 2; break
            case b: h = (r - g) / d + 4; break
        }
        h /= 6
    }

    const hDeg = Math.round(h * 360)
    const sPercent = Math.round(s * 100)
    const lPercent = Math.round(l * 100)

    return `${hDeg} ${sPercent}% ${lPercent}%`
}

/**
 * Adjusts the lightness of an HSL color
 */
function adjustLightness(hslString: string, adjustment: number): string {
    const match = hslString.match(/(\d+)\s+(\d+)%\s+(\d+)%/)
    if (!match || match.length < 4) return hslString

    const h = parseInt(match[1]!)
    const s = parseInt(match[2]!)
    const l = Math.max(0, Math.min(100, parseInt(match[3]!) + adjustment))

    return `${h} ${s}% ${l}%`
}

/**
 * Determines appropriate foreground color based on background lightness
 */
function getForegroundColor(hslString: string): string {
    const match = hslString.match(/(\d+)\s+(\d+)%\s+(\d+)%/)
    if (!match || match.length < 4) return '222.2 47.4% 11.2%' // Default dark

    const lightness = parseInt(match[3]!)
    return lightness > 50 ? '222.2 47.4% 11.2%' : '210 40% 98%' // Dark text for light bg, light text for dark bg
}

/**
 * Generates dynamic CSS variables based on site settings color configuration
 */
export function generateDynamicColorCSS(siteSettings: any): string {
    // Support both old colorScheme structure and new themeSettings structure
    const themeSettings = siteSettings?.themeSettings || siteSettings?.colorScheme || {}

    if (!themeSettings?.customColors) {
        return '' // Return empty string if custom colors are not enabled
    }

    const {
        primaryColor = '#015A86',
        secondaryColor = '#6B7280'
    } = themeSettings

    // Convert to HSL
    const primaryHsl = hexToHsl(primaryColor)
    const secondaryHsl = hexToHsl(secondaryColor)

    // Auto-generate light theme colors (slightly darker for better contrast)
    const lightPrimary = adjustLightness(primaryHsl, -5)
    const lightSecondary = adjustLightness(secondaryHsl, 0)

    // Auto-generate dark theme colors (slightly lighter for better contrast)
    const darkPrimary = adjustLightness(primaryHsl, 10)
    const darkSecondary = adjustLightness(secondaryHsl, 15)

    // Auto-generate foreground colors based on background lightness
    const lightPrimaryFg = getForegroundColor(lightPrimary)
    const lightSecondaryFg = getForegroundColor(lightSecondary)
    const darkPrimaryFg = getForegroundColor(darkPrimary)
    const darkSecondaryFg = getForegroundColor(darkSecondary)

    return `
    :root {
      --primary: ${lightPrimary};
      --primary-foreground: ${lightPrimaryFg};
      --secondary: ${lightSecondary};
      --secondary-foreground: ${lightSecondaryFg};
    }

    [data-theme='dark'] {
      --primary: ${darkPrimary};
      --primary-foreground: ${darkPrimaryFg};
      --secondary: ${darkSecondary};
      --secondary-foreground: ${darkSecondaryFg};
    }
  `
}

/**
 * Generates inline style object with CSS custom properties
 * Alternative approach for component-level styling
 */
export function generateDynamicColorStyles(siteSettings: any) {
    const { colorScheme } = siteSettings || {}

    if (!colorScheme?.customColors) {
        return {}
    }

    const {
        primaryColor = '#015A86',
        primaryColorLight,
        primaryColorDark = '#0A7BB8',
        secondaryColor = '#6B7280',
        secondaryColorLight,
        secondaryColorDark = '#9CA3AF'
    } = colorScheme

    const lightPrimary = primaryColorLight || primaryColor
    const darkPrimary = primaryColorDark || primaryColor
    const lightSecondary = secondaryColorLight || secondaryColor
    const darkSecondary = secondaryColorDark || secondaryColor

    return {
        '--custom-primary-light': lightPrimary,
        '--custom-primary-dark': darkPrimary,
        '--custom-secondary-light': lightSecondary,
        '--custom-secondary-dark': darkSecondary,
        '--primary': hexToHsl(lightPrimary),
        '--secondary': hexToHsl(lightSecondary),
    } as React.CSSProperties
}