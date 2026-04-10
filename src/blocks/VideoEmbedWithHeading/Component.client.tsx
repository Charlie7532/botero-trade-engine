"use client"

import React from "react"
import { motion } from "framer-motion"
import { cn } from "@/utilities/ui"
import type { VideoEmbedWithHeading as VideoEmbedWithHeadingBlockProps } from 'src/payload-types'

const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.3,
        },
    },
}

const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: {
        y: 0,
        opacity: 1,
        transition: {
            type: "spring" as const,
            stiffness: 100,
        },
    },
}

type Props = {
    className?: string,
    headingClassName?: string,
    highlightTextClassName?: string,
    videoClassName?: string,
} & VideoEmbedWithHeadingBlockProps

function isNumber(str: string | null | undefined): boolean {
    if (!str) return false
    return /^\d+(\.\d+)?$/.test(str.trim())
}

const VideoEmbedWithHeadingClient: React.FC<Props> = ({ className, headingClassName, highlightTextClassName, videoClassName, heading, video }) => {
    return (
        <motion.section
            className="py-24 max-w-5xl mx-auto"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.3 }}
            variants={containerVariants}
        >
            <div className={cn(className, "mx-auto px-4 sm:px-6 lg:px-8")}>
                {heading && heading.length > 0 && <motion.h2 className={cn({ "mb-14 w-full text-center text-3xl sm:mx-auto sm:mb-10 sm:w-4/5": !headingClassName }, headingClassName, "text-center mb-12")} variants={itemVariants}>
                    {heading?.map((el, index) => {
                        if (el.highlight && el.text) {
                            return (
                                <React.Fragment key={index}>
                                    {index > 0 && ' '}
                                    <span
                                        className={cn({ "text-transparent bg-clip-text bg-gradient-to-r from-[#7F654C] to-[#B79778]": !highlightTextClassName }, highlightTextClassName)}>
                                        {el.text}
                                    </span>
                                </React.Fragment>
                            )
                        }

                        if (el.text) {
                            return (
                                <React.Fragment key={index}>
                                    {index > 0 && ' '}
                                    {el.text}
                                </React.Fragment>
                            )
                        }

                        return null
                    })}
                </motion.h2>}
                <motion.div variants={itemVariants}
                    whileHover={{ scale: 1.02 }}
                    transition={{ type: "tween", ease: "easeOut", duration: 0.3 }}>
                    <div className="w-full flex justify-center">
                        <iframe
                            width={
                                video.width && isNumber(video.width)
                                    ? Number(video.width.trim())
                                    : video.width
                                        ? video.width.trim()
                                        : "100%"
                            }
                            height={
                                video.height && isNumber(video.height)
                                    ? Number(video.height.trim())
                                    : video.height
                                        ? video.height.trim()
                                        : typeof video.width === "string" ? "auto" : 500
                            }
                            src={video.url}
                            title={video.title || "Video player"}
                            style={{ border: "none" }}
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen={video.allowFullScreen ?? true}
                            className={cn("aspect-video", {
                                "rounded-xl shadow-2xl overflow-hidden": !videoClassName,
                            }, videoClassName,)}
                        />
                    </div>
                </motion.div>
            </div>
        </motion.section>
    )
}

export default VideoEmbedWithHeadingClient;