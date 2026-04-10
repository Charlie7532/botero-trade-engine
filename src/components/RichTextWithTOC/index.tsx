import React from 'react'
import { MediaBlock } from '@/blocks/MediaBlock/Component'
import {
    DefaultNodeTypes,
    SerializedBlockNode,
    SerializedLinkNode,
    type DefaultTypedEditorState,
} from '@payloadcms/richtext-lexical'
import {
    JSXConvertersFunction,
    LinkJSXConverter,
    RichText as ConvertRichText,
} from '@payloadcms/richtext-lexical/react'

import { CodeBlock, CodeBlockProps } from '@/blocks/Code/Component'

import type {
    BannerBlock as BannerBlockProps,
    CallToActionBlock as CTABlockProps,
    MediaBlock as MediaBlockProps,
} from '@/payload-types'
import { BannerBlock } from '@/blocks/Banner/Component'
import { CallToActionBlock } from '@/blocks/CallToAction/Component'
import { cn } from '@/utilities/ui'
import { toKebabCase } from '@/utilities/toKebabCase'

type NodeTypes =
    | DefaultNodeTypes
    | SerializedBlockNode<CTABlockProps | MediaBlockProps | BannerBlockProps | CodeBlockProps>

const internalDocToHref = ({ linkNode }: { linkNode: SerializedLinkNode }) => {
    const { value, relationTo } = linkNode.fields.doc!
    if (typeof value !== 'object') {
        throw new Error('Expected value to be an object')
    }
    const slug = value.slug
    return relationTo === 'posts' ? `/posts/${slug}` : `/${slug}`
}

const jsxConverters: JSXConvertersFunction<NodeTypes> = ({ defaultConverters }) => ({
    ...defaultConverters,
    ...LinkJSXConverter({ internalDocToHref }),
    blocks: {
        banner: ({ node }) => <BannerBlock className="col-start-2 mb-4" {...node.fields} />,
        mediaBlock: ({ node }) => (
            <MediaBlock
                className="col-start-1 col-span-3"
                imgClassName="m-0"
                {...node.fields}
                captionClassName="mx-auto max-w-[48rem]"
                enableGutter={false}
                disableInnerContainer={true}
            />
        ),
        code: ({ node }) => <CodeBlock className="col-start-2" {...node.fields} />,
        cta: ({ node }) => <CallToActionBlock {...node.fields} />,
    },
    heading: ({ node, converters: _converters }) => {
        const Tag = node.tag as keyof React.JSX.IntrinsicElements

        // Extract text content directly from node children for ID generation
        const extractTextFromNode = (children: any[]): string => {
            return children.map((child: any) => {
                if (typeof child === 'string') return child
                if (child?.type === 'text') return child.text || ''
                if (child?.children) return extractTextFromNode(child.children)
                return ''
            }).join('')
        }

        const text = extractTextFromNode(node.children || [])

        // Render children manually since we can't call defaultConverters.heading properly
        const renderChildren = (children: any[]): React.ReactNode[] => {
            return children.map((child: any, index: number) => {
                if (typeof child === 'string') return child
                if (child?.type === 'text') return child.text || ''
                // For more complex nodes, you might need to handle them differently
                return child.text || String(index)
            })
        }

        const children = renderChildren(node.children || [])

        // Only add IDs to H2 headings for the table of contents
        if (Tag === 'h2' && text.trim()) {
            const id = toKebabCase(text.trim())
            return <Tag id={id}>{children}</Tag>
        }

        return <Tag>{children}</Tag>
    },
})

type Props = {
    data: DefaultTypedEditorState
    enableGutter?: boolean
    enableProse?: boolean
} & React.HTMLAttributes<HTMLDivElement>

export default function RichTextWithTOC(props: Props) {
    const { className, enableProse = true, enableGutter = true, ...rest } = props
    return (
        <ConvertRichText
            converters={jsxConverters}
            className={cn(
                'payload-richtext',
                {
                    container: enableGutter,
                    'max-w-none': !enableGutter,
                    'mx-auto prose md:prose-md dark:prose-invert': enableProse,
                },
                className,
            )}
            {...rest}
        />
    )
}
