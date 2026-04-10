import type { PricingCard } from "@/payload-types";
import React from "react";
import { PricingCardClient } from "./Component.client"

type Props = {
    className?: string,
} & PricingCard

export const PricingCardBlock: React.FC<PricingCard> = (props) => {
    return <PricingCardClient {...props} />
}