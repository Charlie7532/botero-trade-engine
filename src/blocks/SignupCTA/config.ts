import type { Block } from 'payload'

export const SignupCTABlock: Block = {
  slug: 'signupCTA',
  imageURL: '/assets/blocks/svg/signup-cta-block.svg',
  imageAltText: 'A signup call-to-action block with user avatars and buttons',
  labels: {
    singular: 'Signup CTA',
    plural: 'Signup CTAs',
  },

  fields: [
    {
      name: 'title',
      type: 'text',
      label: 'Title',
      required: true,
      admin: {
        description: 'Main heading text for the signup CTA section',
      },
    },
    {
      name: 'subtitle',
      type: 'text',
      label: 'Subtitle (Optional)',
      required: false,
      admin: {
        description: 'Optional subtitle text above the main title',
      },
    },
    {
      name: 'buttons',
      type: 'array',
      label: 'Call-to-Action Buttons',
      minRows: 1,
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
          label: 'Icon (for secondary buttons)',
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
          ],
          defaultValue: 'none',
          admin: {
            condition: (_: any, siblingData: any) => siblingData?.style === 'secondary',
            description: 'Icon to display in secondary buttons',
          },
        },
      ],
    },
    {
      name: 'showUserAvatars',
      type: 'checkbox',
      label: 'Show User Avatars',
      defaultValue: true,
      admin: {
        description: 'Display overlapping user avatar images above the title',
      },
    },
  ],
}
