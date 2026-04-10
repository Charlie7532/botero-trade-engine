import { Block } from "payload";
import { PricingCard } from "@/blocks/PricingCard/config";
import { FixedToolbarFeature, InlineToolbarFeature, lexicalEditor } from "@payloadcms/richtext-lexical";

export const PricingPlansGrid: Block = {
    slug: "pricingPlanGrid",
    interfaceName: "PricingPlanGrid",
    imageURL: '/assets/blocks/svg/pricing-plans-grid-block.svg',
    fields: [
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
            name: "description",
            type: "richText",
            required: true,
            editor: lexicalEditor({
                features: ({ rootFeatures }) => {
                    return [
                        ...rootFeatures,
                        FixedToolbarFeature(),
                        InlineToolbarFeature(),
                    ]
                }
            }),
            admin: {
                description: "Paragraph under the heading",
            },
        },
        {
            name: "pricingCards",
            type: "blocks",
            required: true,
            blocks: [
                PricingCard
            ]
        },
    ]
}