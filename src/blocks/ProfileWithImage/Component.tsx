import type { ProfileWithImageBlock as ProfileWithImageBlockProps } from 'src/payload-types'
import React from 'react'
import { ProfileWithImageClient } from './Component.client'


type Props = {
    className?: string
} & ProfileWithImageBlockProps

export const ProfileWithImageBlock: React.FC<Props> = (props) => {
    return (
        <ProfileWithImageClient {...props} />
    )
}
