"use client"
import React from 'react'
import { ServiceCardGridBlock } from '@/payload-types'
import { motion } from 'framer-motion'
import { ServiceCardClient } from '@/blocks/ServiceCardBlock/Component.client'

export const ServiceCardGridClient: React.FC<ServiceCardGridBlock> = ({
    sectionHeader,
    heading,
    serviceCards,
}) => {
    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, amount: 0.3 }} // 👈 Only triggers once, does not reset
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="min-h-screen max-w-6xl mx-auto flex flex-col items-center justify-center"
        >
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.5 }} // 👈 Only animates once
                transition={{ duration: 1, delay: 0.2 }}
                className="min-w-24 px-6 text-center"
            >
                {sectionHeader && (
                    <span className={'block text-sm uppercase mb-2 tracking-wide text-[#9E7F5F]'}>
                        {sectionHeader}
                    </span>
                )}
                {heading && heading.length > 0 && <h2 className={"mb-6 w-full text-center sm:mx-auto sm:mb-4 sm:w-4/5 mt-2 text-4xl font-extrabold tracking-tight text-gray-900 sm:text-4xl"}>
                    {heading?.map((el, index) => {
                        if (el.highlight && el.text) {
                            return (
                                <React.Fragment key={index}>
                                    {index > 0 && ' '}
                                    <span
                                        className={"text-transparent bg-clip-text bg-gradient-to-r from-[#9E7F5F] to-[#B79778]"}>
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
            </motion.div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 w-full mx-auto mt-4">
                {
                    serviceCards.map((block, index) => {
                        return (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 50 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true, amount: 0.5 }}
                                transition={{ duration: 0.8, delay: 0.9 }}
                            >
                                <ServiceCardClient {...block} />
                            </motion.div>
                        )
                    })
                }
            </div>
        </motion.div>
    )
}
