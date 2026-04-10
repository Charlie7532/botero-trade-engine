'use client'

import { Button as HeroButton, Link as HeroLink } from '@heroui/react'
import { buttonVariants as heroButtonVariants } from '@heroui/styles'
import { cn } from '@/utilities/ui'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

// Keep buttonVariants for backward compatibility with components like pagination
// These are Tailwind classes that style native elements (not HeroUI)
const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    defaultVariants: {
      size: 'default',
      variant: 'default',
    },
    variants: {
      size: {
        clear: '',
        default: 'h-10 px-4 py-2',
        icon: 'h-10 w-10',
        lg: 'h-11 rounded-md px-8',
        sm: 'h-9 rounded-md px-3',
      },
      variant: {
        default: 'bg-[var(--accent)] text-[var(--accent-foreground)] hover:opacity-90',
        primary: 'bg-[var(--accent)] text-[var(--accent-foreground)] hover:opacity-90',
        destructive: 'bg-[var(--danger)] text-[var(--danger-foreground)] hover:opacity-90',
        ghost: 'hover:bg-[var(--surface-secondary)] hover:text-[var(--foreground)]',
        link: 'text-[var(--accent)] underline-offset-4 hover:underline',
        outline: 'border border-[var(--border)] bg-transparent hover:bg-[var(--surface-secondary)]',
        secondary: 'bg-[var(--surface-secondary)] text-[var(--foreground)] hover:opacity-90',
      },
    },
  },
)

// Map our variant names to HeroUI v3 variants
type OurVariant = 'default' | 'primary' | 'secondary' | 'destructive' | 'outline' | 'ghost' | 'link'
type HeroVariant = 'primary' | 'secondary' | 'tertiary' | 'outline' | 'ghost' | 'danger' | 'danger-soft'

const variantMap: Record<OurVariant, HeroVariant> = {
  default: 'primary', // Primary/accent solid (default in HeroUI)
  primary: 'primary', // Primary/accent solid
  secondary: 'secondary',
  destructive: 'danger',
  outline: 'outline',
  ghost: 'ghost',
  link: 'ghost',
}

// Map our size names to HeroUI sizes
type OurSize = 'default' | 'sm' | 'lg' | 'icon' | 'clear'
type HeroSize = 'sm' | 'md' | 'lg'

const sizeMap: Record<OurSize, HeroSize> = {
  default: 'md',
  sm: 'sm',
  lg: 'lg',
  icon: 'md',
  clear: 'md',
}

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'color'> {
  variant?: OurVariant | null
  size?: OurSize | null
  asChild?: boolean
  ref?: React.Ref<HTMLButtonElement>
  startContent?: React.ReactNode
  endContent?: React.ReactNode
  href?: string
}

const Button: React.FC<ButtonProps> = ({
  asChild = false,
  className,
  size,
  variant,
  ref,
  startContent,
  endContent,
  children,
  href,
  disabled,
  onClick,
  type,
  ...props
}) => {
  const heroVariant = variantMap[(variant as OurVariant) || 'default']
  const heroSize = sizeMap[(size as OurSize) || 'default']

  // Extra classes for link variant to look like a link
  const linkClasses = variant === 'link' ? 'underline-offset-4 hover:underline' : ''

  // For links, use HeroUI Link styled with buttonVariants
  if (href) {
    return (
      <HeroLink
        href={href}
        className={cn(
          heroButtonVariants({ variant: heroVariant, size: heroSize }),
          size === 'icon' && 'button--icon-only',
          linkClasses,
          className
        )}
      >
        {startContent}
        {children}
        {endContent}
      </HeroLink>
    )
  }

  // For regular buttons, use HeroUI Button
  return (
    <HeroButton
      ref={ref}
      className={cn(linkClasses, className)}
      variant={heroVariant}
      size={heroSize}
      isIconOnly={size === 'icon'}
      isDisabled={disabled}
      onPress={onClick as () => void}
      type={type}
    >
      {startContent}
      {children}
      {endContent}
    </HeroButton>
  )
}

export { Button, buttonVariants }
