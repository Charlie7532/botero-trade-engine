"use client"

import { motion } from "framer-motion"
import React from "react";
import type { PricingPlanGrid as PricingPlanGridProps } from "@/payload-types";
import RichText from "@/components/RichText";
import { PricingCardClient } from "@/blocks/PricingCard/Component.client";

const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.1,
        },
    },
}

const cardVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
        opacity: 1,
        y: 0,
        transition: {
            duration: 0.5,
            ease: [0.6, -0.05, 0.01, 0.99] as const,
        },
    },
}

export const PricingPlanGridClient: React.FC<PricingPlanGridProps> = ({ heading, description, pricingCards }) => {
    console.log('PricingPlanGrid - pricingCards:', pricingCards)
    console.log('PricingPlanGrid - pricingCards length:', pricingCards?.length)

    return <motion.section
        className="pt-3 pb-12 px-4 "
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
        variants={containerVariants}
    >
        <div className="max-w-7xl mx-auto">
            {/* Header */}
            <motion.div className="text-center mb-16" variants={cardVariants}>
                {heading && heading.length && <h2 className="text-4xl md:text-5xl font-light text-gray-900 mb-6">
                    {heading?.map((el, index) => {
                        if (el.highlight && el.text) {
                            return (
                                <React.Fragment key={index}>
                                    {index > 0 && ' '}
                                    <span
                                        className="text-[#C4A78A] font-medium">
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
                </h2>}

                <RichText data={description}
                    enableGutter={false}
                    className="text-lg text-gray-600 max-w-4xl mx-auto leading-relaxed" />

            </motion.div>

            <motion.div
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16"
                variants={containerVariants}
                initial="hidden"
                animate="visible"
            >
                {pricingCards?.map((cards, index) => {
                    return (
                        <motion.div key={index} variants={cardVariants}>
                            <PricingCardClient {...cards} disableAnimation />
                        </motion.div>
                    )
                })}
            </motion.div>
        </div>
    </motion.section>
}