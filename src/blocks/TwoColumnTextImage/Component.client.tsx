'use client'

import type React from "react"
import Image from "next/image"
import { motion } from "framer-motion"
import type { Media } from "@/payload-types"
import RichText from "@/components/RichText"
import { Button } from "@/components/ui/button"
import { DefaultTypedEditorState } from "@payloadcms/richtext-lexical"

type AnimatedTwoColumnProps = {
    richText: DefaultTypedEditorState
    media: number | Media
    imagePosition?: ("left" | "right") | null
    links?:
    | {
        type?: ("reference" | "custom") | null
        reference?: {
            relationTo: "pages"
            value: number | any
        } | null
        url?: string | null
        label: string
        appearance?: ("default" | "primary" | "secondary" | "outline" | "link") | null
        id?: string | null
    }[]
    | null
}

export const AnimatedTwoColumn: React.FC<AnimatedTwoColumnProps> = ({
    links,
    richText,
    media,
    imagePosition = "right",
}) => {
    const isImageLeft = imagePosition === "left"

    // Animation variants
    const containerVariants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.2,
                delayChildren: 0.1
            }
        }
    }

    const textColumnVariants = {
        hidden: {
            opacity: 0,
            x: isImageLeft ? 50 : -50,
            y: 20
        },
        visible: {
            opacity: 1,
            x: 0,
            y: 0,
            transition: {
                duration: 0.6,
                staggerChildren: 0.15,
                delayChildren: 0.2
            }
        }
    }

    const imageColumnVariants = {
        hidden: {
            opacity: 0,
            x: isImageLeft ? -50 : 50,
            y: 20
        },
        visible: {
            opacity: 1,
            x: 0,
            y: 0,
            transition: {
                duration: 0.6,
                delay: 0.3
            }
        }
    }

    const textElementVariants = {
        hidden: {
            opacity: 0,
            y: 20
        },
        visible: {
            opacity: 1,
            y: 0,
            transition: {
                duration: 0.5
            }
        }
    }

    const linkVariants = {
        hidden: {
            opacity: 0,
            y: 20
        },
        visible: {
            opacity: 1,
            y: 0,
            transition: {
                duration: 0.4
            }
        }
    }

    return (
        <motion.div
            className="grid grid-cols-1 md:grid-cols-12 lg:grid-cols-12 gap-8 lg:gap-16 items-center"
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.2 }}
        >
            {/* Text Column */}
            <motion.div
                className={`space-y-6 md:col-span-6 lg:col-span-7 ${isImageLeft ? "lg:order-2" : "lg:order-1"}`}
                variants={textColumnVariants}
            >
                {richText && (
                    <motion.div
                        className="prose prose-gray prose-lg max-w-none dark:prose-invert"
                        variants={textElementVariants}
                    >
                        <RichText className="leading-relaxed" data={richText} enableGutter={false} />
                    </motion.div>
                )}

                {links && links.length > 0 && (
                    <motion.div
                        className="flex flex-col sm:flex-row gap-4 pt-2"
                        variants={textElementVariants}
                    >
                        {links.map((link, i: number) => {
                            // Determine href
                            const href = link.type === 'reference' && link.reference?.value
                                ? typeof link.reference.value === 'object' && 'slug' in link.reference.value
                                    ? `/${link.reference.value.slug}`
                                    : '#'
                                : link.url || '#'

                            // Map appearance to our button variant
                            const variant = link.appearance === 'default' ? 'primary' : (link.appearance || 'primary')

                            return (
                                <motion.div
                                    key={i}
                                    variants={linkVariants}
                                    whileHover={{ scale: 1.05 }}
                                    whileTap={{ scale: 0.95 }}
                                >
                                    <Button
                                        href={href}
                                        variant={variant}
                                        size="lg"
                                        className="text-base"
                                    >
                                        {link.label}
                                    </Button>
                                </motion.div>
                            )
                        })}
                    </motion.div>
                )}
            </motion.div>

            <motion.div
                className={`md:col-span-6 lg:col-span-5 ${isImageLeft ? "lg:order-1" : "lg:order-2"}`}
                variants={imageColumnVariants}
            >
                <div className="relative">
                    {media && typeof media === "object" && media.url ? (
                        <motion.div
                            className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl bg-gray-100 shadow-2xl"
                            whileHover={{ scale: 1.02 }}
                            transition={{ duration: 0.3 }}
                        >
                            <Image
                                src={media.url}
                                alt={media.alt || "Content image"}
                                fill
                                className="object-cover transition-transform duration-300 hover:scale-105"
                                sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 40vw"
                                priority={false}
                            />
                            {/* Subtle overlay for better text contrast if needed */}
                            <div className="absolute inset-0 bg-gradient-to-t from-black/5 to-transparent" />
                        </motion.div>
                    ) : (
                        <motion.div
                            className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200 shadow-2xl flex items-center justify-center"
                            whileHover={{ scale: 1.02 }}
                            transition={{ duration: 0.3 }}
                        >
                            <div className="text-gray-400 text-center">
                                <svg className="mx-auto h-16 w-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={1}
                                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                                    />
                                </svg>
                                <p className="text-sm font-medium">No image available</p>
                            </div>
                        </motion.div>
                    )}
                </div>
            </motion.div>
        </motion.div>
    )
}
