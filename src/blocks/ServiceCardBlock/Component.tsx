import React from "react";
import { ServiceCardClient } from "./Component.client";
import { ServiceCardBlock as ServiceCardBlockProps } from '@/payload-types'

type Props = {
    className?: string,
} & ServiceCardBlockProps


export const ServiceCardBlock: React.FC<Props> = (props) => {
    return <ServiceCardClient {...props} />
}