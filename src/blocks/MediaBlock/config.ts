import type { Block } from 'payload'

export const MediaBlock: Block = {
  slug: 'mediaBlock',
  imageURL: '/assets/blocks/svg/media-block.svg',
  imageAltText: 'A media block for displaying images with various settings',
  interfaceName: 'MediaBlock',
  fields: [
    {
      name: 'media',
      type: 'upload',
      relationTo: 'media',
      required: true,
    },
    {
      name: 'width',
      type: 'group',
      label: 'Width Settings',
      fields: [
        {
          name: 'type',
          type: 'select',
          label: 'Width Type',
          defaultValue: 'max',
          options: [
            {
              label: 'Full Width',
              value: 'full',
            },
            {
              label: 'Max Width',
              value: 'max',
            },
          ],
          admin: {
            description: 'Choose whether the image should span the full width or be constrained to a maximum width',
          },
        },
        {
          name: 'preset',
          type: 'select',
          label: 'Width Preset',
          defaultValue: 'custom',
          options: [
            {
              label: 'Custom Width',
              value: 'custom',
            },
            {
              label: '1/2 Width (50%)',
              value: '1/2',
            },
            {
              label: '1/3 Width (33%)',
              value: '1/3',
            },
            {
              label: '2/3 Width (67%)',
              value: '2/3',
            },
            {
              label: '1/4 Width (25%)',
              value: '1/4',
            },
            {
              label: '3/4 Width (75%)',
              value: '3/4',
            },
          ],
          admin: {
            condition: (_, siblingData) => siblingData?.type === 'max',
            description: 'Choose a preset width or select custom to enter a specific pixel value',
          },
        },
        {
          name: 'maxWidth',
          type: 'number',
          label: 'Custom Max Width (px)',
          defaultValue: 896,
          min: 200,
          max: 1920,
          admin: {
            condition: (_, siblingData) => siblingData?.type === 'max' && siblingData?.preset === 'custom',
            description: 'Maximum width in pixels when using custom preset',
          },
        },
        {
          name: 'alignment',
          type: 'select',
          label: 'Alignment',
          defaultValue: 'center',
          options: [
            {
              label: 'Left',
              value: 'left',
            },
            {
              label: 'Center',
              value: 'center',
            },
            {
              label: 'Right',
              value: 'right',
            },
          ],
          admin: {
            condition: (_, siblingData) => siblingData?.type === 'max',
            description: 'Choose the horizontal alignment of the image',
          },
        },
      ],
    },
    {
      name: 'aspectRatio',
      type: 'select',
      label: 'Aspect Ratio',
      defaultValue: 'auto',
      options: [
        {
          label: 'Auto (Original)',
          value: 'auto',
        },
        {
          label: '16:9 (Widescreen)',
          value: '16/9',
        },
        {
          label: '4:3 (Standard)',
          value: '4/3',
        },
        {
          label: '1:1 (Square)',
          value: '1/1',
        },
        {
          label: '3:2 (Photo)',
          value: '3/2',
        },
        {
          label: '2:3 (Portrait)',
          value: '2/3',
        },
        {
          label: '21:9 (Ultra-wide)',
          value: '21/9',
        },
      ],
      admin: {
        description: 'Choose the aspect ratio for the image. Auto preserves the original ratio.',
      },
    },
    {
      name: 'shadow',
      type: 'select',
      label: 'Shadow',
      defaultValue: 'none',
      options: [
        {
          label: 'None',
          value: 'none',
        },
        {
          label: 'Small',
          value: 'small',
        },
        {
          label: 'Medium',
          value: 'medium',
        },
        {
          label: 'Large',
          value: 'large',
        },
      ],
      admin: {
        description: 'Choose the shadow size for the image',
      },
    },
    {
      name: 'showBorder',
      type: 'checkbox',
      label: 'Show Border',
      defaultValue: true,
      admin: {
        description: 'Toggle the border around the image',
      },
    },
  ],
}
