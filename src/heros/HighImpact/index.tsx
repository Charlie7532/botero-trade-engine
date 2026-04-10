"use client"

import { useHeaderTheme } from "@/providers/HeaderTheme"
import type React from "react"
import { useEffect } from "react"
import type { Page } from "@/payload-types"
import { CMSLink } from "@/components/Link"
import { Media } from "@/components/Media"
import RichText from "@/components/RichText"
import { motion, useScroll, useTransform } from "framer-motion"

export const HighImpactHero: React.FC<Page["hero"]> = ({ links, media, richText }) => {
  const { setHeaderTheme } = useHeaderTheme()
  const { scrollY } = useScroll()

  // Parallax effect for background
  const backgroundY = useTransform(scrollY, [0, 500], [0, 150])
  const contentY = useTransform(scrollY, [0, 500], [0, -50])

  useEffect(() => {
    setHeaderTheme("dark")
  })

  return (
    <div
      className="relative -mt-[10.4rem] flex items-center justify-center text-white overflow-hidden"
      data-theme="dark"
    >
      {/* Background Media with Parallax */}
      <motion.div className="absolute inset-0 min-h-[100vh]" style={{ y: backgroundY }}>
        {media && typeof media === "object" && (
          <>
            <Media fill imgClassName="object-cover" priority resource={media} />

            {/* Simplified overlays with direct animation props */}
            <motion.div
              className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/20 to-black/60"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8 }}
            />
            <motion.div
              className="absolute inset-0 bg-gradient-to-r from-black/30 via-transparent to-black/30"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.3 }}
            />
            <motion.div
              className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-primary/20"
              animate={{
                opacity: [0.3, 0.6, 0.3],
              }}
              transition={{
                duration: 8,
                repeat: Number.POSITIVE_INFINITY,
              }}
            />
          </>
        )}
      </motion.div>

      {/* Content Container with Parallax */}
      <motion.div
        className="container relative z-10 flex items-center justify-center min-h-[100vh] px-4 sm:px-6 lg:px-8"
        style={{ y: contentY }}
      >
        <motion.div
          className="max-w-4xl mx-auto text-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6 }}
        >
          {/* Main Content */}
          <div className="space-y-8">
            {richText && (
              <motion.div
                className="space-y-6"
                initial={{ opacity: 0, y: 30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.8, delay: 0.2 }}
              >
                <RichText
                  className="text-white drop-shadow-2xl [&_h1]:text-4xl sm:[&_h1]:text-5xl md:[&_h1]:text-6xl lg:[&_h1]:text-7xl [&_h1]:font-bold [&_h1]:leading-tight [&_h1]:tracking-tight [&_h1]:mb-6 [&_p]:text-lg sm:[&_p]:text-xl md:[&_p]:text-2xl [&_p]:text-white/90 [&_p]:leading-relaxed [&_p]:max-w-3xl [&_p]:mx-auto"
                  data={richText}
                  enableGutter={false}
                />
              </motion.div>
            )}

            {/* Enhanced CTA Buttons using your design system colors */}
            {Array.isArray(links) && links.length > 0 && (
              <motion.div
                className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-6 pt-8"
                initial={{ opacity: 0, y: 30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.8, delay: 0.4 }}
              >
                {links.map(({ link }, i) => {
                  const isPrimary = i === 0
                  return (
                    <motion.div
                      key={i}
                      className="group relative overflow-hidden rounded-full"
                      initial={{ opacity: 0, y: 20, scale: 0.9 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{
                        duration: 0.6,
                        delay: 0.6 + i * 0.1,
                      }}
                      whileHover={{
                        scale: 1.05,
                        y: -2,
                        transition: { duration: 0.2 },
                      }}
                      whileTap={{
                        scale: 0.95,
                        transition: { duration: 0.1 },
                      }}
                    >
                      {isPrimary && (
                        <motion.div
                          className="absolute inset-0 bg-primary rounded-full blur-xl opacity-50"
                          animate={{
                            opacity: [0.5, 0.8, 0.5],
                            scale: [1, 1.05, 1],
                          }}
                          transition={{
                            duration: 3,
                            repeat: Number.POSITIVE_INFINITY,
                          }}
                        />
                      )}
                      <CMSLink
                        {...link}
                        className={`
                          relative inline-flex items-center justify-center px-8 py-4 text-base font-semibold rounded-full transition-all duration-300 shadow-2xl
                          ${isPrimary
                            ? "bg-primary text-primary-foreground border-2 border-white/20 hover:bg-primary/90"
                            : "bg-white/10 text-white border-2 border-white/30 backdrop-blur-sm hover:bg-white/20"
                          }
                        `}
                      />
                    </motion.div>
                  )
                })}
              </motion.div>
            )}
          </div>

          {/* Simplified Scroll Indicator */}
          <motion.div
            className="absolute bottom-8 left-1/2 transform -translate-x-1/2"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2, duration: 1 }}
          >
            <motion.div
              className="w-6 h-10 border-2 border-white/50 rounded-full flex justify-center cursor-pointer hover:border-primary/80 transition-colors"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.95 }}
              animate={{
                y: [0, 10, 0],
              }}
              transition={{
                duration: 2,
                repeat: Number.POSITIVE_INFINITY,
              }}
            >
              <motion.div
                className="w-1 h-3 bg-white/70 rounded-full mt-2"
                animate={{
                  opacity: [0.7, 1, 0.7],
                  height: ["12px", "16px", "12px"],
                }}
                transition={{
                  duration: 2,
                  repeat: Number.POSITIVE_INFINITY,
                }}
              />
            </motion.div>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  )
}
