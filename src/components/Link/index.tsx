'use client'

import { Button } from '@/components/ui/button'
import { cn } from '@/utilities/ui'
import Link from 'next/link'
import React from 'react'

import type { Page, Post } from '@/payload-types'

type CMSLinkType = {
  appearance?: 'inline' | 'default' | 'primary' | 'secondary' | 'outline' | 'link' | 'destructive' | 'ghost' | null
  children?: React.ReactNode
  className?: string
  label?: string | null
  newTab?: boolean | null
  reference?: {
    relationTo: 'pages' | 'posts'
    value: Page | Post | string | number
  } | null
  size?: 'sm' | 'md' | 'lg' | null
  type?: 'custom' | 'reference' | null
  url?: string | null
}

// Map CMS size to our button size
const sizeMap: Record<string, 'sm' | 'default' | 'lg'> = {
  sm: 'sm',
  md: 'default',
  lg: 'lg',
}

export const CMSLink: React.FC<CMSLinkType> = (props) => {
  const {
    type,
    appearance: appearanceFromProps,
    children,
    className,
    label,
    newTab,
    reference,
    size: sizeFromProps,
    url,
  } = props

  // Default to 'inline' if appearance is null or undefined
  const appearance = appearanceFromProps || 'inline'

  const href =
    type === 'reference' && typeof reference?.value === 'object' && reference.value.slug
      ? `${reference?.relationTo !== 'pages' ? `/${reference?.relationTo}` : ''}/${reference.value.slug
      }`
      : url

  if (!href) return null

  const newTabProps = newTab ? { rel: 'noopener noreferrer', target: '_blank' } : {}

  /* Ensure we don't break any styles set by richText */
  if (appearance === 'inline') {
    return (
      <Link className={cn(className)} href={href || url || ''} {...newTabProps}>
        {label && label}
        {children && children}
      </Link>
    )
  }

  // Map appearance to button variant (they match except 'default' maps to 'primary')
  const variant = appearance === 'default' ? 'primary' : appearance
  const size = sizeMap[sizeFromProps || 'md'] || 'default'

  return (
    <Button
      as={Link}
      href={href || url || ''}
      className={className}
      size={size}
      variant={variant}
      {...(newTabProps as any)}
    >
      {label && label}
      {children && children}
    </Button>
  )
}
