import { generatePreviewPath } from '../../utilities/generatePreviewPath'
import type { GeneratePreviewURL, LivePreviewConfig } from 'payload'

export const postLivePreview: LivePreviewConfig = {
  url: ({ data, req }) =>
    generatePreviewPath({
      slug: typeof data?.slug === 'string' ? data.slug : '',
      collection: 'posts',
      req,
    }),
}

export const postPreview: GeneratePreviewURL = (data: any, { req }) =>
  generatePreviewPath({
    slug: typeof data?.slug === 'string' ? data.slug : '',
    collection: 'posts',
    req,
  })
