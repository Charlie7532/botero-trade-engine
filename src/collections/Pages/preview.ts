import { generatePreviewPath } from '../../utilities/generatePreviewPath'
import type { GeneratePreviewURL, LivePreviewConfig } from 'payload'

export const pageLivePreview: LivePreviewConfig = {
  url: ({ data, req }) =>
    generatePreviewPath({
      slug: typeof data?.slug === 'string' ? data.slug : '',
      collection: 'pages',
      req,
    }),
}

export const pagePreview: GeneratePreviewURL = (data: any, { req }) =>
  generatePreviewPath({
    slug: typeof data?.slug === 'string' ? data.slug : '',
    collection: 'pages',
    req,
  })
