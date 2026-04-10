'use client'

import React from 'react'
import RichText from '@/components/RichText'
import TableOfContents, { type TocPosition } from '@/components/TableOfContents'
import { RelatedPosts } from '@/blocks/RelatedPosts/Component'
import type { Post } from '@/payload-types'

interface PostArticleProps {
    post: Post
    tocPosition?: TocPosition
}

export default function PostArticle({ post, tocPosition = 'none' }: PostArticleProps) {
    // Return simple layout when TOC is disabled
    if (tocPosition === 'none') {
        return (
            <div className="flex flex-col items-center gap-4 pt-8">
                <div className="container">
                    <div className="max-w-[48rem] mx-auto">
                        <RichText data={post.content} enableGutter={false} />
                    </div>
                    {post.relatedPosts && post.relatedPosts.length > 0 && (
                        <RelatedPosts
                            className="mt-12 max-w-[52rem] mx-auto"
                            docs={post.relatedPosts.filter((post) => typeof post === 'object')}
                        />
                    )}
                </div>
            </div>
        )
    }

    // Layout with table of contents
    const gridCols = tocPosition === 'left' ? 'lg:grid-cols-[280px_1fr]' : 'lg:grid-cols-[1fr_280px]'

    return (
        <div className="flex flex-col items-center gap-4 pt-8">
            <div className="container">
                <div className={`lg:grid ${gridCols} lg:gap-8 xl:gap-12`}>
                    {tocPosition === 'left' && (
                        <div className="lg:order-1">
                            <TableOfContents position="left" />
                        </div>
                    )}
                    <div className={`max-w-[48rem] mx-auto lg:mx-0 ${tocPosition === 'left' ? 'lg:order-2' : ''}`}>
                        <RichText data={post.content} enableGutter={false} />
                    </div>
                    {tocPosition === 'right' && (
                        <div className="lg:order-2">
                            <TableOfContents position="right" />
                        </div>
                    )}
                </div>
                {post.relatedPosts && post.relatedPosts.length > 0 && (
                    <RelatedPosts
                        className="mt-12 max-w-[52rem] mx-auto"
                        docs={post.relatedPosts.filter((post) => typeof post === 'object')}
                    />
                )}
            </div>
        </div>
    )
}
