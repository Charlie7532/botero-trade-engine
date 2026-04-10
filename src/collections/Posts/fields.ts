import { Field } from 'payload'

import {
  BlocksFeature,
  FixedToolbarFeature,
  HeadingFeature,
  HorizontalRuleFeature,
  InlineToolbarFeature,
  lexicalEditor,
} from '@payloadcms/richtext-lexical'

import { Banner } from '../../blocks/Banner/config'
import { Code } from '../../blocks/Code/config'
import { MediaBlock } from '../../blocks/MediaBlock/config'

import {
  MetaDescriptionField,
  MetaImageField,
  MetaTitleField,
  OverviewField,
  PreviewField,
} from '@payloadcms/plugin-seo/fields'
import { slugField } from '@/fields/slug'

export const postsFields: Field[] = [
  {
    name: 'title',
    type: 'text',
    required: true,
  },
  {
    type: 'tabs',
    tabs: [
      {
        fields: [
          {
            name: 'heroImage',
            type: 'upload',
            relationTo: 'media',
          },
          {
            name: 'content',
            type: 'richText',
            editor: lexicalEditor({
              features: ({ rootFeatures }) => {
                return [
                  ...rootFeatures,
                  HeadingFeature({ enabledHeadingSizes: ['h1', 'h2', 'h3', 'h4'] }),
                  BlocksFeature({ blocks: [Banner, Code, MediaBlock] }),
                  FixedToolbarFeature(),
                  InlineToolbarFeature(),
                  HorizontalRuleFeature(),
                ]
              },
            }),
            label: false,
            required: true,
          },
        ],
        label: 'Content',
      },
      {
        fields: [
          {
            name: 'relatedPosts',
            type: 'relationship',
            admin: {
              position: 'sidebar',
            },
            filterOptions: ({ id }) => {
              return {
                id: {
                  not_in: [id],
                },
              }
            },
            hasMany: true,
            relationTo: 'posts',
          },
          {
            name: 'categories',
            type: 'relationship',
            admin: {
              position: 'sidebar',
            },
            hasMany: true,
            relationTo: 'categories',
          },
        ],
        label: 'Meta',
      },
      {
        name: 'meta',
        label: 'SEO',
        fields: [
          OverviewField({
            titlePath: 'meta.title',
            descriptionPath: 'meta.description',
            imagePath: 'meta.image',
          }),
          MetaTitleField({
            hasGenerateFn: true,
          }),
          MetaImageField({
            relationTo: 'media',
          }),
          MetaDescriptionField({}),
          PreviewField({
            hasGenerateFn: true,
            titlePath: 'meta.title',
            descriptionPath: 'meta.description',
          }),
        ],
      },
    ],
  },
  {
    name: 'publishedAt',
    type: 'date',
    admin: {
      date: {
        pickerAppearance: 'dayAndTime',
      },
      position: 'sidebar',
    },
    hooks: {
      beforeChange: [
        ({ siblingData, value }) => {
          if (siblingData._status === 'published' && !value) {
            return new Date()
          }
          return value
        },
      ],
    },
  },
  {
    name: 'authors',
    type: 'relationship',
    admin: {
      position: 'sidebar',
    },
    hasMany: true,
    relationTo: 'users',
  },
  {
    name: 'populatedAuthors',
    type: 'array',
    access: {
      update: () => false,
    },
    admin: {
      disabled: true,
      readOnly: true,
    },
    fields: [
      {
        name: 'id',
        type: 'text',
      },
      {
        name: 'name',
        type: 'text',
      },
    ],
  },
  ...slugField(),
]
