import { FixedToolbarFeature, InlineToolbarFeature, lexicalEditor } from "@payloadcms/richtext-lexical";
import type { Block } from "payload";

export const ProfileWithImage: Block = {
    slug: "profileWithImage",
    interfaceName: "ProfileWithImageBlock",
    imageURL: '/assets/blocks/svg/profile-with-image-block.svg',
    imageAltText: "A profile section with image, heading, subheading and content.",
    fields: [
        {
            name: "heading",
            type: "text",
            required: true,
        },
        {
            name: "subHeading",
            type: "group",
            fields: [
                {
                    name: "text",
                    type: "text",
                },
                {
                    name: "heighlight",
                    type: "checkbox",
                    defaultValue: true,
                }
            ]
        },
        {
            name: "content",
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
            })
        },
        {
            name: 'media',
            type: 'upload',
            relationTo: 'media',
            required: true,
        },
        {
            name: "mediaDisplayAlignment",
            type: "select",
            options: ["left", "right"],
            defaultValue: "right",
            required: true,
        }
    ]
}