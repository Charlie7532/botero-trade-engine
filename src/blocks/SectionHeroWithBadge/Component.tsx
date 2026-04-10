
import type { SectionHeroWithBadge as SectionHeroWithBadgeProps } from "@/payload-types"
import React from "react"
import { SectionHeroWithBadgeClient } from "./Component.client"

export const SectionHeroWithBadgeBlock: React.FC<SectionHeroWithBadgeProps> = (props) => {
    return <SectionHeroWithBadgeClient {...props} />
}