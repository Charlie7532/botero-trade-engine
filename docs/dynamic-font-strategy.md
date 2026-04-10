# Dynamic Font Strategy Documentation

This document outlines the comprehensive strategy for implementing dynamic fonts in the Payload CMS project, allowing administrators to customize typography throughout the site with Google Fonts integration.

## Overview

The dynamic font system allows site administrators to:
- Enable/disable custom fonts
- Select different font families and weights for headings and body text
- Automatically generate Google Fonts links with optimized subsets
- Apply font settings via CSS variables at runtime

## Implementation Components

### 1. Admin Configuration (SiteSettings)

The font configuration is stored in the `SiteSettings` global document within a nested structure:

```typescript
// Inside SiteSettings config.ts
{
  name: 'themeSettings',
  type: 'group',
  fields: [
    // Other theme settings...
    {
      name: 'fonts',
      type: 'group',
      label: 'Typography',
      fields: [
        {
          name: 'customFonts',
          type: 'checkbox',
          label: 'Enable Custom Fonts',
          defaultValue: false,
          admin: {
            description: 'Enable this to customize fonts and weights for different elements of your site',
          },
        },
        {
          name: 'fontSlots',
          type: 'array',
          label: 'Font Slots',
          admin: {
            description: 'Configure font families and weights for different elements of your site',
            condition: (_, siblingData) => siblingData.customFonts === true,
            components: {
              RowLabel: '{{label}}: {{font}} ({{weight}})',
            },
            initCollapsed: true,
          },
          defaultValue: [
            {
              slotKey: 'h1',
              label: 'Heading 1',
              font: 'Inter',
              weight: '700',
            },
            {
              slotKey: 'h2',
              label: 'Heading 2',
              font: 'Inter',
              weight: '600',
            },
            {
              slotKey: 'h3',
              label: 'Heading 3',
              font: 'Inter',
              weight: '500',
            },
            {
              slotKey: 'body',
              label: 'Body Text',
              font: 'Inter',
              weight: '400',
            }
          ],
          fields: [
            {
              name: 'slotKey',
              type: 'text',
              label: 'Element Key',
              required: true,
              admin: {
                description: 'CSS variable identifier (e.g., h1, h2, body)',
                readOnly: true,
              },
            },
            {
              name: 'label',
              type: 'text',
              label: 'Display Label',
              required: true,
              admin: {
                readOnly: true,
              },
            },
            {
              name: 'font',
              type: 'select',
              label: 'Font Family',
              required: true,
              options: [
                { label: 'Inter', value: 'Inter' },
                { label: 'Roboto', value: 'Roboto' },
                { label: 'Open Sans', value: 'Open Sans' },
                { label: 'Lato', value: 'Lato' },
                { label: 'Montserrat', value: 'Montserrat' },
                { label: 'Source Sans Pro', value: 'Source Sans Pro' },
                { label: 'Source Serif Pro', value: 'Source Serif Pro' },
                { label: 'Oswald', value: 'Oswald' },
                { label: 'Raleway', value: 'Raleway' },
                { label: 'Nunito', value: 'Nunito' },
                { label: 'Merriweather', value: 'Merriweather' },
              ],
            },
            {
              name: 'weight',
              type: 'select',
              label: 'Font Weight',
              required: true,
              options: [
                { label: 'Light (300)', value: '300' },
                { label: 'Regular (400)', value: '400' },
                { label: 'Medium (500)', value: '500' },
                { label: 'Semi-Bold (600)', value: '600' },
                { label: 'Bold (700)', value: '700' },
                { label: 'Extra Bold (800)', value: '800' },
              ],
            },
          ],
        },
      ],
    }
  ]
}
```

### 2. Font Utilities (dynamicStyles.ts)

The dynamic font utilities handle generating CSS variables and Google Fonts links from the configuration:

```typescript
// src/utilities/dynamicStyles.ts

// Generate CSS variables for fonts
export function generateFontVariables(siteSettings: any): string {
  if (!siteSettings?.themeSettings?.fonts?.fontSlots) {
    return '';
  }

  const { fontSlots } = siteSettings.themeSettings.fonts;
  
  let cssVariables = '';
  
  // Process each font slot (h1, h2, h3, body)
  fontSlots.forEach((slotData: any) => {
    const { slotKey, font, weight } = slotData;
    if (slotKey && font) {
      cssVariables += `  --font-${slotKey}: ${font};\n`;
    }
    if (slotKey && weight) {
      cssVariables += `  --font-weight-${slotKey}: ${weight};\n`;
    }
  });
  
  return cssVariables ? `
:root {
${cssVariables}}
` : '';
}

// Generate Google Fonts URL from site settings
export function generateGoogleFontsLink(siteSettings: any): string {
  if (!siteSettings?.themeSettings?.fonts?.fontSlots) {
    return '';
  }
  
  const { fontSlots } = siteSettings.themeSettings.fonts;
  const fontFamilies = new Map<string, Set<string>>();
  
  // Collect unique font families and weights
  fontSlots.forEach((slot: any) => {
    const { font, weight } = slot;
    if (font && weight) {
      if (!fontFamilies.has(font)) {
        fontFamilies.set(font, new Set());
      }
      fontFamilies.get(font)?.add(weight);
    }
  });
  
  // No fonts to load
  if (fontFamilies.size === 0) {
    return '';
  }
  
  // Build the Google Fonts URL
  const fontParams = Array.from(fontFamilies.entries()).map(([family, weights]) => {
    // Replace spaces with + for URL
    const encodedFamily = family.replace(/ /g, '+');
    // Join weights with comma
    const weightString = Array.from(weights).join(',');
    return `family=${encodedFamily}:wght@${weightString}`;
  }).join('&');
  
  return `https://fonts.googleapis.com/css2?${fontParams}&display=swap`;
}
```

### 3. Client-Side Font Injection (DynamicStyles.tsx)

The React component that injects the font styles and Google Fonts link into the document head:

```tsx
// src/components/DynamicStyles.tsx
'use client'

import { useEffect } from 'react';
import { generateFontVariables, generateGoogleFontsLink } from '@/utilities/dynamicStyles';

interface DynamicStylesProps {
  siteSettings: any;
}

export function DynamicStyles({ siteSettings }: DynamicStylesProps) {
  useEffect(() => {
    // Font styles
    const fontStyles = generateFontVariables(siteSettings);
    if (fontStyles) {
      // Remove existing font styles
      const existingFontStyle = document.getElementById('dynamic-font-styles');
      if (existingFontStyle) {
        existingFontStyle.remove();
      }

      // Inject new font styles
      const styleElement = document.createElement('style');
      styleElement.id = 'dynamic-font-styles';
      styleElement.textContent = fontStyles;
      document.head.appendChild(styleElement);
    }

    // Google Fonts
    const googleFontsUrl = generateGoogleFontsLink(siteSettings);
    const existingFontLink = document.querySelector('link#dynamic-google-fonts');
    if (existingFontLink) {
      existingFontLink.remove();
    }

    if (googleFontsUrl) {
      const linkElement = document.createElement('link');
      linkElement.id = 'dynamic-google-fonts';
      linkElement.rel = 'stylesheet';
      linkElement.href = googleFontsUrl;
      document.head.appendChild(linkElement);
    }

  }, [siteSettings]);

  return null; // This component doesn't render anything
}
```

### 4. CSS Application (globals.css)

The CSS that applies the font variables to the relevant HTML elements:

```css
/* src/app/(frontend)/globals.css */
@layer base {
  /* Apply font variables to elements */
  h1 {
    font-family: var(--font-h1, inherit);
    font-weight: var(--font-weight-h1, 700);
  }
  
  h2 {
    font-family: var(--font-h2, inherit);
    font-weight: var(--font-weight-h2, 600);
  }
  
  h3 {
    font-family: var(--font-h3, inherit);
    font-weight: var(--font-weight-h3, 500);
  }
  
  body {
    font-family: var(--font-body, inherit);
    font-weight: var(--font-weight-body, 400);
  }
}
```

### 5. Usage in Layout/Root Component

The DynamicStyles component should be included in the root layout or a high-level component with access to the site settings:

```tsx
// In a high-level component or layout
import { DynamicStyles } from '@/components/DynamicStyles';

export default function Layout({ siteSettings }) {
  return (
    <>
      <DynamicStyles siteSettings={siteSettings} />
      {/* Rest of your application */}
    </>
  )
}
```

## Implementation Steps

When implementing this system, follow these steps:

1. **Add the config to SiteSettings**:
   - Create the font configuration structure in `src/globals/SiteSettings/config.ts`
   - Define default font settings for h1, h2, h3, and body

2. **Create the utility functions**:
   - Implement `generateFontVariables` and `generateGoogleFontsLink` in `src/utilities/dynamicStyles.ts`
   - Add proper typing for parameters and return values

3. **Create the DynamicStyles component**:
   - Implement the client-side component for font injection
   - Ensure it properly removes existing styles before adding new ones
   - Handle conditional loading of Google Fonts

4. **Update the CSS**:
   - Add CSS variable usage for font family and weight in `globals.css`
   - Set appropriate fallback values

5. **Add to layout**:
   - Include the DynamicStyles component in the appropriate layout or root component
   - Pass site settings data from the server to the component

## Extension Points

The system can be extended in the following ways:

1. **Additional Typography Properties**:
   - Add support for font size, line height, letter spacing
   - Include responsive typography settings

2. **More Font Sources**:
   - Support for self-hosted fonts
   - Integration with other font providers like Adobe Fonts

3. **Font Preloading**:
   - Add font preloading for critical paths
   - Implement font-display strategies

4. **Performance Optimizations**:
   - Subset optimization for language-specific character sets
   - Font loading strategies to minimize CLS (Cumulative Layout Shift)

## Troubleshooting

Common issues that may arise:

1. **Google Fonts Not Loading**:
   - Check that the URL is properly constructed
   - Verify that the font family and weight selections are valid
   - Inspect network requests to confirm fonts are being requested

2. **Font Variables Not Applied**:
   - Verify that CSS variables are being properly generated
   - Check that the variables are being applied to the correct elements
   - Ensure specificity is not causing the styles to be overridden

3. **Missing Font Weights**:
   - Confirm that selected font families support the requested weights
   - Check for console errors related to missing font resources

## Best Practices

1. **Performance**:
   - Only load the necessary font weights
   - Consider using the `display=swap` parameter for Google Fonts
   - Implement font preloading for critical fonts

2. **Accessibility**:
   - Ensure text remains readable at different zoom levels
   - Maintain appropriate contrast ratios with background colors
   - Consider using system fonts as fallbacks

3. **Maintenance**:
   - Document font choices and rationale
   - Keep the font selection curated and limited
   - Test font rendering across different devices and browsers

---

This implementation provides a flexible system for managing typography throughout the site with a user-friendly admin interface while ensuring optimal loading performance and maintainability.