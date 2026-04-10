'use client'

import type { BannerBlock as BannerBlockProps } from 'src/payload-types'

import { Alert } from '@heroui/react'
import { cn } from '@/utilities/ui'
import React from 'react'
import RichText from '@/components/RichText'

type Props = {
  className?: string
} & BannerBlockProps

// Map banner style to HeroUI Alert color
const colorMap: Record<string, 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger'> = {
  info: 'default',
  error: 'danger',
  success: 'success',
  warning: 'warning',
}

export const BannerBlock: React.FC<Props> = ({ className, content, style }) => {
  return (
    <div className={cn('mx-auto my-8 w-full', className)}>
      <Alert color={colorMap[style || 'info'] || 'default'}>
        <RichText data={content} enableGutter={false} enableProse={false} />
      </Alert>
    </div>
  )
}
