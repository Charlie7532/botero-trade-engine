'use client'

import React from 'react'
import { ServiceCardBlock } from '@/payload-types'
import { CardBody, CardContainer, CardItem } from '@/components/ui/3d-card'
import { Media } from '@/components/Media'
import Link from 'next/link'
import { cn } from '@/utilities/ui'

type ServiceCardBlockProps = {
    className?: string
} & ServiceCardBlock

export const ServiceCardClient: React.FC<ServiceCardBlockProps> = ({
    className,
    title,
    description,
    image,
    primaryButton,
    secondaryButton,
}) => {
    const isSecondaryButtonExists = (secondaryButton &&
        Object.values(secondaryButton)
            .map((val) => !!val)
            .filter(Boolean).length &&
        secondaryButton.text)

    const isPrimaryButtonExists = (primaryButton &&
        Object.values(primaryButton)
            .map((val) => !!val)
            .filter(Boolean).length &&
        primaryButton.text)

    const isButtonValuePresent =
        isPrimaryButtonExists || isSecondaryButtonExists


    return (
        <CardContainer className={cn("inter-var", className)}>
            <CardBody className={"bg-gray-50 relative group/card  dark:hover:shadow-2xl dark:hover:shadow-emerald-500/[0.1] dark:bg-black dark:border-white/[0.2] border-black/[0.1] w-full max-w-[25rem] h-auto rounded-xl p-6 border"}>
                <CardItem translateZ="50" className="text-xl font-bold text-neutral-600 dark:text-white">
                    {title}
                </CardItem>
                <CardItem
                    as="p"
                    translateZ="60"
                    className="text-neutral-500 text-sm max-w-sm mt-2 dark:text-neutral-300"
                >
                    {description}
                </CardItem>
                <CardItem translateZ="100" className="w-full mt-4">
                    {/* <Image
                    src="/assets/photos/private_event_venue_2.webp"
                    height="1000"
                    width="1000"
                    className="h-60 w-full object-cover rounded-xl group-hover/card:shadow-xl"
                    alt="thumbnail"
                /> */}
                    <Media
                        resource={image}
                        size="1000"
                        imgClassName="h-60 w-full object-cover rounded-xl group-hover/card:shadow-xl"
                        alt="thumbnail"
                    />
                </CardItem>

                {isButtonValuePresent &&
                    <div className="flex justify-between items-center mt-20">
                        {isSecondaryButtonExists && <CardItem
                            translateZ={20}
                            as={Link}
                            href={secondaryButton.href}
                            className="px-4 py-2 rounded-xl text-xs font-normal dark:text-white"
                        >
                            {secondaryButton.text}
                        </CardItem>}
                        {isPrimaryButtonExists && <CardItem translateZ={20}>
                            {/* <ModalBtn className="bg-black text-white" eventType="private">
                                Start planning
                            </ModalBtn> */}
                            <CardItem
                                translateZ={20}
                                as={Link}
                                href={primaryButton.href}
                                className="px-4 py-2 rounded-xl bg-black text-white"
                            >
                                {primaryButton.text}
                            </CardItem>
                        </CardItem>}
                    </div>
                }
            </CardBody>
        </CardContainer>
    )
}
