import { Block } from "payload";

export const VideoEmbedWithHeading: Block = {
    slug: "videoEmbedWithHeading",
    interfaceName: "VideoEmbedWithHeading",
    imageURL: '/assets/blocks/svg/video-with-heading-block.svg',
    fields: [
        {
            name: "heading",
            type: "array",
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
            name: "video",
            type: "group",
            required: true,
            fields: [
                {
                    name: "url",
                    type: "text",
                    required: true,
                },
                {
                    name: "title",
                    type: "text",
                    required: true,
                },
                {
                    name: "allowFullScreen",
                    type: "checkbox",
                    defaultValue: true,
                },
                {
                    name: "width",
                    type: "text",
                    defaultValue: "100%",
                },
                {
                    name: "height",
                    type: "text",
                },
            ]
        }
    ]
}