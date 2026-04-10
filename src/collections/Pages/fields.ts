import { Field } from 'payload'

import { Archive } from '../../blocks/ArchiveBlock/config'
import { CallToAction } from '../../blocks/CallToAction/config'
import { Content } from '../../blocks/Content/config'
import { FormBlock } from '../../blocks/Form/config'
import { MediaBlock } from '../../blocks/MediaBlock/config'
import { SignupCTABlock } from '../../blocks/SignupCTA/config'
import { TwoColumnTextImageBlock } from '../../blocks/TwoColumnTextImage/config'
import { hero } from '@/heros/config'
import { slugField } from '@/fields/slug'

import {
  MetaDescriptionField,
  MetaImageField,
  MetaTitleField,
  OverviewField,
  PreviewField,
} from '@payloadcms/plugin-seo/fields'
import { ProfileWithImage } from '@/blocks/ProfileWithImage/config'
import { VideoEmbedWithHeading } from '@/blocks/VideoEmbedWithHeading/config'
import { PricingPlansGrid } from '@/blocks/PricingPlansGrid/config'
import { SectionHeroWithBadge } from '@/blocks/SectionHeroWithBadge/config'
import { ServiceCardGridBlock } from '@/blocks/ServiceCardGridBlock/config'

export const pagesFields: Field[] = [
  {
    name: 'title',
    type: 'text',
    required: true,
  },
  {
    type: 'tabs',
    tabs: [
      {
        fields: [hero],
        label: 'Hero',
      },
      {
        fields: [
          {
            name: 'layout',
            type: 'blocks',
            blocks: [
              CallToAction,
              Content,
              MediaBlock,
              Archive,
              FormBlock,
              SignupCTABlock,
              TwoColumnTextImageBlock,
              ProfileWithImage,
              VideoEmbedWithHeading,
              PricingPlansGrid,
              SectionHeroWithBadge,
              ServiceCardGridBlock,
            ],
            required: true,
            admin: {
              initCollapsed: true,
            },
          },
        ],
        label: 'Content',
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
      position: 'sidebar',
    },
  },
  ...slugField(),
]
