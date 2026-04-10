import type { Block } from 'payload'

import {
  FixedToolbarFeature,
  HeadingFeature,
  InlineToolbarFeature,
  lexicalEditor,
} from '@payloadcms/richtext-lexical'

export const TwoColumnTextImageBlock: Block = {
  slug: 'twoColumnTextImage',
  imageURL: '/assets/blocks/svg/two-column-text-image-block.svg',
  imageAltText: 'A two-column layout with text and image',
  labels: {
    singular: 'Two Column Text Image',
    plural: 'Two Column Text Images',
  },

  fields: [
    {
      name: 'richText',
      type: 'richText',
      label: 'Rich Text Content',
      required: true,
      editor: lexicalEditor({
        features: ({ rootFeatures }) => {
          return [
            ...rootFeatures,
            HeadingFeature({ enabledHeadingSizes: ['h1', 'h2', 'h3'] }),
            FixedToolbarFeature(),
            InlineToolbarFeature(),
          ]
        },
      }),
    },
    {
      name: 'media',
      type: 'upload',
      relationTo: 'media',
      label: 'Image',
      required: true,
    },
    {
      name: 'imagePosition',
      type: 'radio',
      label: 'Image Position',
      options: [
        {
          label: 'Left',
          value: 'left',
        },
        {
          label: 'Right',
          value: 'right',
        },
      ],
      defaultValue: 'right',
      admin: {
        layout: 'horizontal',
        description: 'Choose whether the image appears on the left or right side of the text',
      },
    },
    {
      name: 'links',
      type: 'array',
      label: 'Call-to-Action Links',
      maxRows: 3,
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
          label: 'Link Label',
          required: true,
        },
        {
          name: 'appearance',
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
      ],
    },
  ],
}
