import { Block } from "payload";

export const ServiceCardBlock: Block = {
    slug: "serviceCard",
    interfaceName: "ServiceCardBlock",
    imageURL: '/assets/blocks/svg/service-card-block.svg',
    fields: [
        {
            name: "title",
            type: "text",
            required: true,
        },
        {
            name: "description",
            type: "textarea",
            required: true,
        },
        {
            name: 'image',
            type: 'upload',
            relationTo: 'media',
            required: true,
        },
        {
            name: "primaryButton",
            type: "group",
            fields: [
                {
                    name: "text",
                    type: "text",
                    defaultValue: "Start planning"
                },
                {
                    name: "href",
                    type: "text",
                    validate: (
                        value: unknown,
                        { siblingData }: { siblingData?: any }
                    ): true | string => {
                        if (siblingData?.text && (!value || value === "")) {
                            return "Href Link Path is required";
                        }
                        return true;
                    },
                },
            ]
        },
        {
            name: "secondaryButton",
            type: "group",
            fields: [
                {
                    name: "text",
                    type: "text",
                    defaultValue: "Learn more →"
                },
                {
                    name: "href",
                    type: "text",
                    validate: (
                        value: unknown,
                        { siblingData }: { siblingData?: any }
                    ): true | string => {
                        if (siblingData?.text && (!value || value === "")) {
                            return "Href Link Path is required";
                        }
                        return true;
                    },
                },
            ]
        }
    ]
}