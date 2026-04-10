import type { VideoEmbedWithHeading as VideoEmbedWithHeadingBlockProps } from 'src/payload-types'
import React from 'react'
import VideoEmbedWithHeadingClient from './Component.client'

type Props = {
    className?: string,
    headingClassName?: string,
    highlightTextClassName?: string,
    videoClassName?: string,
} & VideoEmbedWithHeadingBlockProps


export const VideoEmbedWithHeadingBlock: React.FC<Props> = (props) => {
    return (
        <>
            <VideoEmbedWithHeadingClient {...props} />
        </>
    )
}