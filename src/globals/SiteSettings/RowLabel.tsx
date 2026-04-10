'use client'
import { SiteSetting } from '@/payload-types'
import { RowLabelProps, useRowLabel } from '@payloadcms/ui'
import { SocialMediaIcon } from '@/components/SocialMediaIcons'

type PlatformArray = NonNullable<NonNullable<SiteSetting['socialMedia']>['platforms']>
type PlatformItem = PlatformArray[number]

const PLATFORM_NAMES: Record<PlatformItem['platform'], string> = {
  facebook: 'Facebook',
  twitter: 'Twitter/X',
  instagram: 'Instagram',
  linkedin: 'LinkedIn',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  github: 'GitHub',
  discord: 'Discord',
}

// We no longer use emoji icons; we'll render the project's SocialMediaIcon component

export const RowLabel: React.FC<RowLabelProps> = () => {
  // useRowLabel gives us the row data for an array item inside the SiteSettings global
  const data = useRowLabel<PlatformItem>()

  const platformKey = data?.data?.platform as PlatformItem['platform'] | undefined
  let label = 'Platform'

  if (platformKey && PLATFORM_NAMES[platformKey]) {
    label = PLATFORM_NAMES[platformKey]
  } else if (data) {
    // Fallback to numbered label like "Platform 01"
    label = `Platform ${data.rowNumber !== undefined ? (data.rowNumber + 1).toString().padStart(2, '0') : ''}`
  }

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
      {platformKey ? (
        <span style={{ display: 'inline-flex', alignItems: 'center', lineHeight: 0 }}>
          <SocialMediaIcon platform={platformKey} size={16} style={{ display: 'block' }} />
        </span>
      ) : null}
      <span style={{ fontSize: 13, lineHeight: '14px' }}>{label}</span>
    </div>
  )
}
