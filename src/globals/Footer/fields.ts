import type { Field } from 'payload'
import { link } from '@/fields/link'

const logo: Field = {
  name: 'logo',
  type: 'group',
  label: 'Footer Logo Settings',
  fields: [
    {
      name: 'overrideSiteLogo',
      type: 'checkbox',
      label: 'Override Site Logo',
      admin: {
        description: 'Check to use a different logo for the footer instead of the global site logo',
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
        description: 'Choose how you want to configure your footer logos',
      },
    },
    {
      name: 'customLogo',
      type: 'upload',
      relationTo: 'media',
      label: 'Custom Footer Logo',
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
      defaultValue: 100,
      min: 30,
      max: 300,
      admin: {
        description: 'Set the desired height of the footer logo (width will auto-adjust to maintain aspect ratio)',
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
      RowLabel: '@/globals/Footer/RowLabel#RowLabel',
    },
  },
}

export const footerFields: Field[] = [
  {
    type: 'tabs',
    tabs: [
      {
        label: 'Navigation',
        fields: [navItems],
      },
      {
        label: 'Branding',
        fields: [logo],
      },
    ],
  },
]
