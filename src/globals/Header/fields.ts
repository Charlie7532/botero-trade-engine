import type { Field } from 'payload'
import { link } from '@/fields/link'

const headerStyle: Field = {
  name: 'headerStyle',
  type: 'select',
  label: 'Header Style',
  defaultValue: 'default',
  options: [
    {
      label: 'Default - Centered Logo & Navigation',
      value: 'default',
    },
    {
      label: 'Modern - Full Width with Blur',
      value: 'modern',
    },
    {
      label: 'Minimal - Clean & Simple',
      value: 'minimal',
    },
    {
      label: 'Full Width - Stretched to Edges',
      value: 'fullWidth',
    },
  ],
  admin: {
    description: 'Choose the header layout and styling approach',
  },
}

const logo: Field = {
  name: 'logo',
  type: 'group',
  label: 'Header Logo Settings',
  fields: [
    {
      name: 'overrideSiteLogo',
      type: 'checkbox',
      label: 'Override Site Logo',
      admin: {
        description: 'Check to use a different logo for the header instead of the global site logo',
      },
    },
    {
      name: 'logoMode',
      type: 'select',
      label: 'Logo Configuration',
      required: true,
      defaultValue: 'simple',
      options: [
        {
          label: 'Simple (One logo for all themes)',
          value: 'simple',
        },
        {
          label: 'Light/Dark (Different logos for light and dark themes)',
          value: 'lightDark',
        },
      ],
      admin: {
        condition: (data) => data.logo?.overrideSiteLogo,
        description: 'Choose how you want to configure your header logos',
      },
    },
    {
      name: 'customLogo',
      type: 'upload',
      relationTo: 'media',
      label: 'Custom Header Logo',
      admin: {
        condition: (data) => data.logo?.overrideSiteLogo && data.logo?.logoMode === 'simple',
      },
    },
    {
      type: 'row',
      fields: [
        {
          name: 'customLogoLight',
          type: 'upload',
          relationTo: 'media',
          label: 'Light Mode Logo',
          admin: {
            condition: (data) => data.logo?.overrideSiteLogo && data.logo?.logoMode === 'lightDark',
            width: '50%',
          },
        },
        {
          name: 'customLogoDark',
          type: 'upload',
          relationTo: 'media',
          label: 'Dark Mode Logo',
          admin: {
            condition: (data) => data.logo?.overrideSiteLogo && data.logo?.logoMode === 'lightDark',
            width: '50%',
          },
        },
      ],
    },
    {
      name: 'height',
      type: 'number',
      label: 'Logo Height (px)',
      defaultValue: 40,
      min: 20,
      max: 100,
      admin: {
        description: 'Set the desired height of the header logo (width will auto-adjust to maintain aspect ratio)',
      },
    },
  ],
}

const navItems: Field = {
  name: 'navItems',
  type: 'array',
  fields: [
    link({
      appearances: false,
    }),
  ],
  maxRows: 6,
  admin: {
    initCollapsed: true,
    components: {
      RowLabel: '@/globals/Header/RowLabel#RowLabel',
    },
  },
}

const ctaButtons: Field = {
  name: 'buttons',
  type: 'array',
  label: 'Call-to-Action Buttons',
  minRows: 1,
  maxRows: 3,
  admin: {
    initCollapsed: true,
  },
  fields: [
    {
      name: 'type',
      type: 'radio',
      options: [
        {
          label: 'Internal Link',
          value: 'reference',
        },
        {
          label: 'Custom URL',
          value: 'custom',
        },
      ],
      defaultValue: 'reference',
      admin: {
        layout: 'horizontal',
      },
    },
    {
      name: 'reference',
      type: 'relationship',
      relationTo: ['pages'],
      required: true,
      admin: {
        condition: (_: any, siblingData: any) => siblingData?.type === 'reference',
      },
    },
    {
      name: 'url',
      type: 'text',
      label: 'Custom URL',
      required: true,
      admin: {
        condition: (_: any, siblingData: any) => siblingData?.type === 'custom',
      },
    },
    {
      name: 'label',
      type: 'text',
      label: 'Button Label',
      required: true,
    },
    {
      name: 'style',
      type: 'select',
      defaultValue: 'primary',
      options: [
        {
          label: 'Default',
          value: 'default',
        },
        {
          label: 'Primary',
          value: 'primary',
        },
        {
          label: 'Secondary',
          value: 'secondary',
        },
        {
          label: 'Outline',
          value: 'outline',
        },
        {
          label: 'Link',
          value: 'link',
        },
      ],
    },
    {
      name: 'icon',
      type: 'select',
      label: 'Button Icon',
      options: [
        {
          label: 'None',
          value: 'none',
        },
        {
          label: 'Google',
          value: 'google',
        },
        {
          label: 'Email',
          value: 'email',
        },
        {
          label: 'Search',
          value: 'search',
        },
        {
          label: 'User',
          value: 'user',
        },
        {
          label: 'Arrow Right',
          value: 'arrow-right',
        },
        {
          label: 'External Link',
          value: 'external-link',
        },
        {
          label: 'Chevron Right',
          value: 'chevron-right',
        },
      ],
      defaultValue: 'none',
      admin: {
        description: 'Choose an icon to display in the button',
      },
    },
    {
      name: 'iconPosition',
      type: 'select',
      label: 'Icon Position',
      options: [
        {
          label: 'Before Text',
          value: 'before',
        },
        {
          label: 'After Text',
          value: 'after',
        },
        {
          label: 'Icon Only (No Text)',
          value: 'only',
        },
      ],
      defaultValue: 'before',
      admin: {
        condition: (_: any, siblingData: any) => siblingData?.icon && siblingData?.icon !== 'none',
        description: 'Choose where to position the icon relative to the text',
      },
    },
  ],
}

// Flat array of setting fields, no longer wrapped in a Group
const settingsFields: Field[] = [
  {
    name: 'sticky',
    type: 'checkbox',
    label: 'Make Header Sticky',
    defaultValue: false,
    admin: {
      description: 'Enable to make the header stick to the top when scrolling',
    },
  },
  {
    name: 'backgroundType',
    type: 'select',
    label: 'Background Type',
    defaultValue: 'transparent',
    options: [
      {
        label: 'Transparent',
        value: 'transparent',
      },
      {
        label: 'Semi-transparent',
        value: 'semi-transparent',
      },
      {
        label: 'Solid Color',
        value: 'solid',
      },
    ],
    admin: {
      description: 'Choose the header background transparency level',
    },
  },
  {
    name: 'backgroundColor',
    type: 'text',
    label: 'Background Color',
    admin: {
      description: 'Hex color code (e.g., #000000) or CSS color name. Used for solid and semi-transparent backgrounds.',
      placeholder: '#ffffff',
      condition: (data) => data.backgroundType !== 'transparent',
    },
  },
  {
    name: 'textColor',
    type: 'select',
    label: 'Text Color Theme',
    defaultValue: 'auto',
    options: [
      {
        label: 'Automatic (Black in light theme, White in dark theme)',
        value: 'auto',
      },
      {
        label: 'Primary Color (Use site primary color)',
        value: 'primary',
      },
      {
        label: 'Custom Color',
        value: 'custom',
      },
    ],
    admin: {
      description: 'Choose the text color scheme for the header navigation and content',
    },
  },
  {
    name: 'customTextColor',
    type: 'text',
    label: 'Custom Text Color',
    admin: {
      description: 'Enter a hex color code (e.g., #FF0000) for custom text color',
      placeholder: '#000000',
      condition: (data) => data.textColor === 'custom',
      components: {
        Field: {
          path: '@/components/fields/ColorPicker',
        },
      },
    },
  },
  {
    name: 'menuPosition',
    type: 'select',
    label: 'Menu Position',
    defaultValue: 'right',
    options: [
      {
        label: 'Left - Menu aligned to the left',
        value: 'left',
      },
      {
        label: 'Center - Menu centered in header',
        value: 'center',
      },
      {
        label: 'Right - Menu aligned to the right',
        value: 'right',
      },
    ],
    admin: {
      description: 'Choose where to position the navigation menu in the header',
    },
  },
  {
    name: 'showSearchBar',
    type: 'checkbox',
    label: 'Show Search Icon',
    defaultValue: true,
    admin: {
      description: 'Enable to show the search icon in the header navigation',
    },
  },
]

export const headerFields: Field[] = [
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Navigation',
        fields: [navItems, ctaButtons],
      },
      {
        label: 'Branding',
        fields: [logo],
      },
      {
        label: 'Settings',
        fields: [headerStyle, ...settingsFields],
      },
    ],
  },
]
