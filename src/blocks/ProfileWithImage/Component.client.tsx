'use client'
import { cn } from '@/utilities/ui'
import { Media } from '@/components/Media'
import RichText from '@/components/RichText'
import React from 'react'
import type { ProfileWithImageBlock as ProfileWithImageBlockProps } from 'src/payload-types'
import { motion } from 'framer-motion'

type Props = {
    className?: string
} & ProfileWithImageBlockProps

// Animation variants
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
    hidden: { y: 30, opacity: 0 },
    visible: {
        y: 0,
        opacity: 1,
        transition: {
            type: 'spring' as const,
            stiffness: 100,
        },
    },
}

export const ProfileWithImageClient: React.FC<Props> = ({
    className,
    heading,
    subHeading,
    content,
    media,
    mediaDisplayAlignment,
}) => {
    return (
        <section className={cn({ "container mx-auto px-44 py-24": !className }, className)}>
            <motion.div
                className="flex flex-col space-y-24"
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, amount: 0.1 }}
                variants={containerVariants}
            >
                <motion.div
                    variants={itemVariants}
                    className={cn(
                        'flex flex-col items-center gap-8 sm:gap-12',
                        {
                            'sm:flex-row': mediaDisplayAlignment === 'left',
                            'sm:flex-row-reverse': mediaDisplayAlignment === 'right',
                        },
                    )}
                >
                    <motion.div
                        className="w-full sm:w-2/5"
                        whileHover={{ scale: 1.03 }}
                        transition={{ type: 'tween', ease: 'easeOut', duration: 0.3 }}
                    >
                        <Media
                            resource={media}
                            imgClassName={cn('h-auto w-full rounded-lg object-cover', {
                                'sm:rounded-tr-[80px] sm:rounded-bl-[80px]': mediaDisplayAlignment === 'left',
                                'sm:rounded-tl-[80px] sm:rounded-br-[80px]': mediaDisplayAlignment === 'right',
                            })}
                        />
                    </motion.div>

                    <div className="w-full text-center sm:w-3/5 sm:text-left">
                        <motion.h3
                            variants={itemVariants}
                            className="mb-1 text-2xl font-bold text-slate-900 dark:text-white"
                        >
                            {heading}
                        </motion.h3>
                        {subHeading?.text && (
                            <motion.p
                                variants={itemVariants}
                                className={cn('mb-4 text-lg font-medium', {
                                    'text-[#C4A78A]': subHeading.heighlight,
                                })}
                            >
                                {subHeading.text}
                            </motion.p>
                        )}
                        <motion.p variants={itemVariants}>
                            <RichText
                                data={content}
                                enableGutter={false}
                                className="leading-relaxed text-slate-700 dark:text-slate-400"
                            />
                        </motion.p>
                    </div>
                </motion.div>
            </motion.div>
        </section>
    )
}
