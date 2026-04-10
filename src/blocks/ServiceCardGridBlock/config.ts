import { Block } from "payload";
import { ServiceCardBlock } from "../ServiceCardBlock/config";

export const ServiceCardGridBlock: Block = {
    slug: "serviceCardGrid",
    interfaceName: "ServiceCardGridBlock",
    imageURL: '/assets/blocks/svg/service-card-grid-block.svg',
    fields: [
        {
            name: "sectionHeader",
            type: "text",
        },
        {
            name: "heading",
            type: "array",
            required: true,
            fields: [
                {
                    name: "text",
                    type: "text",
                    required: true,
                },
                {
                    name: "highlight",
                    type: "checkbox",
                    defaultValue: false,
                }
            ]
        },
        {
            name: "serviceCards",
            type: "blocks",
            blocks: [ServiceCardBlock],
            required: true,
        }
    ]
}