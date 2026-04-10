import React, { Fragment } from 'react'

import type { Page } from '@/payload-types'

import { ArchiveBlock } from '@/blocks/ArchiveBlock/Component'
import { CallToActionBlock } from '@/blocks/CallToAction/Component'
import { ContentBlock } from '@/blocks/Content/Component'
import { FormBlock } from '@/blocks/Form/Component'
import { MediaBlock } from '@/blocks/MediaBlock/Component'
import { SignupCTA } from '@/blocks/SignupCTA/Component'
import { TwoColumnTextImage } from '@/blocks/TwoColumnTextImage/Component'
import { ProfileWithImageBlock } from '@/blocks/ProfileWithImage/Component'
import { VideoEmbedWithHeadingBlock } from '@/blocks/VideoEmbedWithHeading/Component'
import { PricingPlanGridBlock } from '@/blocks/PricingPlansGrid/Component'
import { SectionHeroWithBadgeBlock } from '@/blocks/SectionHeroWithBadge/Component'
import { ServiceCardGridBlock } from '@/blocks/ServiceCardGridBlock/Component'


const blockComponents = {
  archive: ArchiveBlock,
  content: ContentBlock,
  cta: CallToActionBlock,
  formBlock: FormBlock,
  mediaBlock: MediaBlock,
  signupCTA: SignupCTA,
  twoColumnTextImage: TwoColumnTextImage,
  profileWithImage: ProfileWithImageBlock,
  videoEmbedWithHeading: VideoEmbedWithHeadingBlock,
  pricingPlanGrid: PricingPlanGridBlock,
  sectionHeroWithBadge: SectionHeroWithBadgeBlock,
  serviceCardGrid: ServiceCardGridBlock,
}

export const RenderBlocks: React.FC<{
  blocks: Page['layout'][0][]
}> = (props) => {
  const { blocks } = props

  const hasBlocks = blocks && Array.isArray(blocks) && blocks.length > 0

  if (hasBlocks) {
    return (
      <Fragment>
        {blocks.map((block, index) => {
          const { blockType } = block

          if (blockType && blockType in blockComponents) {
            const Block = blockComponents[blockType]

            if (Block) {
              return (
                <div className="my-16" key={index}>
                  {/* @ts-expect-error there may be some mismatch between the expected types here */}
                  <Block {...block} />
                </div>
              )
            }
          }
          return null
        })}
      </Fragment>
    )
  }

  return null
}
