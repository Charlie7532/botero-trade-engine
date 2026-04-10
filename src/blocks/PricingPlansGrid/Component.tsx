import { PricingPlanGrid as PricingPlanGridProps } from "@/payload-types";
import React from "react";
import { PricingPlanGridClient } from "./Component.client";

export const PricingPlanGridBlock: React.FC<PricingPlanGridProps> = (props) => {
    return <PricingPlanGridClient {...props} />
}