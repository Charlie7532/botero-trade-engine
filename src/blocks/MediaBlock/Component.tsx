import type { StaticImageData } from 'next/image'

import { cn } from '@/utilities/ui'
import React from 'react'
import RichText from '@/components/RichText'

import type { MediaBlock as MediaBlockProps } from '@/payload-types'

import { AnimatedMediaBlock } from './Component.client'

type Props = MediaBlockProps & {
  breakout?: boolean
  captionClassName?: string
  className?: string
  enableGutter?: boolean
  imgClassName?: string
  staticImage?: StaticImageData
  disableInnerContainer?: boolean
  width?: {
    type?: 'full' | 'max' | null
    preset?: 'custom' | '1/2' | '1/3' | '2/3' | '1/4' | '3/4' | null
    maxWidth?: number | null
    alignment?: 'left' | 'center' | 'right' | null
  } | null
  shadow?: 'none' | 'small' | 'medium' | 'large' | null
  showBorder?: boolean | null
  alignment?: 'left' | 'center' | 'right' | null
  aspectRatio?: 'auto' | '16/9' | '4/3' | '1/1' | '3/2' | '2/3' | '21/9' | null
}

export const MediaBlock: React.FC<Props> = (props) => {
  const {
    captionClassName,
    className,
    enableGutter = true,
    imgClassName,
    media,
    staticImage,
    disableInnerContainer,
    width,
    aspectRatio,
    shadow,
    showBorder,
  } = props

  let caption
  if (media && typeof media === 'object') caption = media.caption

  return (
    <div
      className={cn(
        '',
        {
          container: enableGutter,
        },
        className,
      )}
    >
      {(media || staticImage) && (
        <AnimatedMediaBlock
          imgClassName={imgClassName}
          media={media}
          staticImage={staticImage}
          width={width}
          aspectRatio={aspectRatio}
          shadow={shadow}
          showBorder={showBorder}
        />
      )}
      {caption && (
        <div
          className={cn(
            'mt-6',
            {
              container: !disableInnerContainer,
            },
            captionClassName,
          )}
        >
          <RichText data={caption} enableGutter={false} />
        </div>
      )}
    </div>
  )
}
