"use client"

import type React from "react"
import type { Page } from "@/payload-types"
import { CMSLink } from "@/components/Link"
import { Media } from "@/components/Media"
import RichText from "@/components/RichText"
import { motion } from "framer-motion"

export const MediumImpactHero: React.FC<Page["hero"]> = ({ links, media, richText }) => {
  return (
    <div className="py-8 md:py-12 lg:py-16">
      <div className="container">
        {/* Side-by-side layout on large screens */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 xl:gap-16 items-center">
          {/* Content Section - Left side on large screens */}
          <motion.div
            className="order-2 lg:order-1"
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8 }}
          >
            {richText && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 0.2 }}
              >
                <RichText
                  className="mb-6 md:mb-8 [&_h1]:text-3xl sm:[&_h1]:text-4xl md:[&_h1]:text-5xl lg:[&_h1]:text-6xl [&_h1]:font-bold [&_h1]:leading-tight [&_h1]:tracking-tight [&_h1]:mb-4 [&_p]:text-lg md:[&_p]:text-xl [&_p]:text-muted-foreground [&_p]:leading-relaxed"
                  data={richText}
                  enableGutter={false}
                />
              </motion.div>
            )}

            {/* Enhanced CTA Buttons using design system */}
            {Array.isArray(links) && links.length > 0 && (
              <motion.ul
                className="flex flex-wrap gap-4 md:gap-6"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 0.4 }}
              >
                {links.map(({ link }, i) => {
                  const isPrimary = i === 0
                  return (
                    <motion.li
                      key={i}
                      initial={{ opacity: 0, y: 20, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{
                        duration: 0.6,
                        delay: 0.6 + i * 0.1,
                      }}
                      whileHover={{
                        scale: 1.02,
                        y: -1,
                        transition: { duration: 0.2 },
                      }}
                      whileTap={{
                        scale: 0.98,
                        transition: { duration: 0.1 },
                      }}
                    >
                      <CMSLink
                        {...link}
                        className={`
                          inline-flex items-center  justify-center px-6 py-3 md:px-8 md:py-4 text-sm md:text-base font-semibold rounded-full transition-all duration-300 shadow-lg hover:shadow-xl
                          ${isPrimary
                            ? "bg-primary text-primary-foreground hover:bg-primary/90 border border-primary/20"
                            : "border-secondary text-secondary-foreground hover:bg-secondary/80 border border-border"
                          }
                        `}
                      />
                    </motion.li>
                  )
                })}
              </motion.ul>
            )}
          </motion.div>

          {/* Media Section - Right side on large screens */}
          <motion.div
            className="order-1 lg:order-2"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
          >
            {media && typeof media === "object" && (
              <div className="relative">
                {/* Image Container with Enhanced Styling */}
                <motion.div
                  className="relative overflow-hidden rounded-xl md:rounded-2xl shadow-2xl"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 1, delay: 0.6 }}
                  whileHover={{
                    scale: 1.02,
                    transition: { duration: 0.3 },
                  }}
                >
                  {/* Subtle gradient overlay for depth */}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/10 via-transparent to-transparent z-10 rounded-xl md:rounded-2xl" />

                  <Media
                    className="w-full"
                    imgClassName="w-full h-auto object-cover transition-transform duration-700 hover:scale-105"
                    priority
                    resource={media}
                  />

                  {/* Decorative border */}
                  <div className="absolute inset-0 rounded-xl md:rounded-2xl border border-white/10" />
                </motion.div>

                {/* Enhanced Caption */}
                {media?.caption && (
                  <motion.div
                    className="mt-4 md:mt-6"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 1 }}
                  >
                    <RichText
                      className="text-sm md:text-base text-muted-foreground [&_p]:leading-relaxed"
                      data={media.caption}
                      enableGutter={false}
                    />
                  </motion.div>
                )}

                {/* Subtle background decoration */}
                <motion.div
                  className="absolute -top-4 -right-4 w-24 h-24 bg-primary/5 rounded-full blur-2xl -z-10"
                  animate={{
                    scale: [1, 1.2, 1],
                    opacity: [0.3, 0.6, 0.3],
                  }}
                  transition={{
                    duration: 4,
                    repeat: Number.POSITIVE_INFINITY,
                  }}
                />
                <motion.div
                  className="absolute -bottom-8 -left-8 w-32 h-32 bg-secondary/5 rounded-full blur-3xl -z-10"
                  animate={{
                    scale: [1.2, 1, 1.2],
                    opacity: [0.2, 0.5, 0.2],
                  }}
                  transition={{
                    duration: 6,
                    repeat: Number.POSITIVE_INFINITY,
                  }}
                />
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  )
}
