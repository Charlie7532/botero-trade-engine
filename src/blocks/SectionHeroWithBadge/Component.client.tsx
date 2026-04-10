"use client"
import { motion } from "framer-motion"
import { Chip } from "@heroui/react"
import React from "react"
import * as LucideIcons from "lucide-react";
import type { SectionHeroWithBadge as SectionHeroWithBadgeProps } from "@/payload-types"
import RichText from "@/components/RichText"
import { Media } from "@/components/Media"


const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.2,
        },
    },
}

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
        opacity: 1,
        y: 0,
        transition: {
            duration: 0.6,
            ease: [0.6, -0.05, 0.01, 0.99] as const,
        },
    },
}

export const SectionHeroWithBadgeClient: React.FC<SectionHeroWithBadgeProps> = ({ heading, highlightHeading, description, image, badge }) => {
    const Icon = badge?.icon ? (LucideIcons as any)[badge.icon] as React.ComponentType<{ className?: string; size?: number }> : null;

    return (
        <motion.section
            className="relative py-20 px-4 text-center"
            initial="hidden"
            animate="visible"
            variants={containerVariants}
        >
            <div className="max-w-4xl mx-auto">
                {badge?.text && <motion.div variants={itemVariants} className="mb-6">
                    <Chip
                        variant="secondary"
                        size="lg"
                        className="mb-4 border border-[#C4A78A] text-[#C4A78A]"
                    >
                        {Icon ? <Icon className="w-4 h-4" /> : <LucideIcons.Sparkles className="w-4 h-4" />}
                        {badge.text}
                    </Chip>
                </motion.div>}

                <motion.h1 variants={itemVariants} className="text-4xl md:text-6xl font-light text-gray-900 mb-6 leading-tight">
                    {heading}
                    <span className="block text-[#C4A78A] font-medium">{highlightHeading}</span>
                </motion.h1>

                <motion.p
                    variants={itemVariants}
                    className="text-lg md:text-xl text-gray-600 max-w-3xl mx-auto leading-relaxed mb-12"
                >
                    <RichText data={description}
                        enableGutter={false} />
                </motion.p>

                <motion.div variants={itemVariants} className="relative w-full max-w-4xl mx-auto">
                    <div className="relative w-full h-[400px] md:h-[500px] rounded-2xl overflow-hidden shadow-2xl">
                        <Media
                            resource={image}
                            imgClassName="rounded shadow-lg object-cover"
                            priority
                            fill
                        />
                    </div>
                </motion.div>
            </div>
        </motion.section>
    )
}