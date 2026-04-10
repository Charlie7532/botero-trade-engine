import React from "react";
import { ServiceCardGridClient } from "./Component.client";
import { ServiceCardGridBlock as ServiceCardGridBlockProps } from '@/payload-types'

type Props = {
    className?: string,
} & ServiceCardGridBlockProps


export const ServiceCardGridBlock: React.FC<Props> = (props) => {
    return <ServiceCardGridClient {...props} />
}