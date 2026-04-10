import { Block } from "payload";
import * as lucideIcons from "lucide-react";

export const PricingCard: Block = {
    slug: "pricingCard",
    interfaceName: "PricingCard",
    imageURL: '/assets/blocks/svg/pricing-card-block.svg',
    fields: [
        {
            name: "icon",
            type: "select",
            options: Object.keys(lucideIcons),
            required: true,
        },
        {
            name: "price",
            type: "number",
            required: true,
        },
        {
            name: "title",
            type: "text",
            required: true,
        },
        {
            name: "subtitle",
            type: "text",
        },
        {
            name: "description",
            type: "text",
            required: true,
        },
        {
            name: "callToAction",
            type: "group",
            required: true,
            fields: [
                {
                    name: "link",
                    type: "text",
                    required: true,
                },
                {
                    name: "text",
                    type: "text",
                    required: true,
                },
                {
                    name: "external",
                    type: "checkbox",
                    defaultValue: false,
                },
            ]
        },
        {
            name: "highlight",
            type: "checkbox",
            defaultValue: false,
        },
        {
            name: "highlightLabel",
            type: "text",
            maxLength: 30,
            admin: {
                condition: (_: any, siblingData: any) => siblingData?.highlight === true,
            },
            validate: (
                value: unknown,
                { siblingData }: { siblingData?: any }
            ): true | string => {
                if (siblingData?.highlight && (!value || value === "")) {
                    return "Highlight label is required when highlight is enabled";
                }
                return true;
            },
        },
    ]
}