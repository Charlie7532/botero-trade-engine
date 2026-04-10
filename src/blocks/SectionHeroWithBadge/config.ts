import { FixedToolbarFeature, InlineToolbarFeature, lexicalEditor } from "@payloadcms/richtext-lexical";
import { Block } from "payload";
import * as lucideIcons from "lucide-react";

export const SectionHeroWithBadge: Block = {
    slug: "sectionHeroWithBadge",
    interfaceName: "SectionHeroWithBadge",
    imageURL: "/assets/blocks/svg/section-hero-with-badge-block.svg",
    fields: [
        {
            name: "heading",
            type: "text",
            required: true,
        },
        {
            name: "highlightHeading",
            type: "text",
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
            name: "badge",
            type: "group",
            admin: {
                description: "Small label above the heading (e.g., 'Our Planning Services')",
            },
            fields: [
                {
                    name: "text",
                    type: "text",
                },
                {
                    name: "icon",
                    type: "select",
                    options: Object.keys(lucideIcons),
                },
            ]
        },
        {
            name: "image",
            type: "upload",
            relationTo: "media",
            required: true,
            admin: {
                description: "Main image displayed below the text",
            },
        },
    ]
}