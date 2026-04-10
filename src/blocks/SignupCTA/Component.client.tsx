'use client'
/* eslint-disable @next/next/no-img-element */

import type React from "react"
import type { Page } from "@/payload-types"
import { CMSLink } from "@/components/Link"
import { Button } from "@/components/ui/button"

type AnimatedSignupCTAProps = {
    title: string
    subtitle?: string | null
    buttons?:
    | {
        type?: ("reference" | "custom") | null
        reference?: {
            relationTo: "pages"
            value: number | Page
        } | null
        url?: string | null
        label: string
        style?: ("default" | "primary" | "secondary" | "outline" | "link") | null
        icon?: ("none" | "google" | "email") | null
        id?: string | null
    }[]
    | null
    showUserAvatars?: boolean | null
}

// Google Icon SVG Component
const GoogleIcon = () => (
    <svg className="w-6" xmlns="http://www.w3.org/2000/svg" viewBox="-0.5 0 48 48" version="1.1">
        <g id="Icons" stroke="none" strokeWidth="1" fill="none" fillRule="evenodd">
            <g id="Color-" transform="translate(-401.000000, -860.000000)">
                <g id="Google" transform="translate(401.000000, 860.000000)">
                    <path d="M9.82727273,24 C9.82727273,22.4757333 10.0804318,21.0144 10.5322727,19.6437333 L2.62345455,13.6042667 C1.08206818,16.7338667 0.213636364,20.2602667 0.213636364,24 C0.213636364,27.7365333 1.081,31.2608 2.62025,34.3882667 L10.5247955,28.3370667 C10.0772273,26.9728 9.82727273,25.5168 9.82727273,24" id="Fill-1" fill="#FBBC05" />
                    <path d="M23.7136364,10.1333333 C27.025,10.1333333 30.0159091,11.3066667 32.3659091,13.2266667 L39.2022727,6.4 C35.0363636,2.77333333 29.6954545,0.533333333 23.7136364,0.533333333 C14.4268636,0.533333333 6.44540909,5.84426667 2.62345455,13.6042667 L10.5322727,19.6437333 C12.3545909,14.112 17.5491591,10.1333333 23.7136364,10.1333333" id="Fill-2" fill="#EB4335" />
                    <path d="M23.7136364,37.8666667 C17.5491591,37.8666667 12.3545909,33.888 10.5322727,28.3562667 L2.62345455,34.3946667 C6.44540909,42.1557333 14.4268636,47.4666667 23.7136364,47.4666667 C29.4455,47.4666667 34.9177955,45.4314667 39.0249545,41.6181333 L31.5177727,35.8144 C29.3995682,37.1488 26.7323182,37.8666667 23.7136364,37.8666667" id="Fill-3" fill="#34A853" />
                    <path d="M46.1454545,24 C46.1454545,22.6133333 45.9318182,21.12 45.6113636,19.7333333 L23.7136364,19.7333333 L23.7136364,28.8 L36.3181818,28.8 C35.6879545,31.8912 33.9724545,34.2677333 31.5177727,35.8144 L39.0249545,41.6181333 C43.3393409,37.6138667 46.1454545,31.6490667 46.1454545,24" id="Fill-4" fill="#4285F4" />
                </g>
            </g>
        </g>
    </svg>
)

// Email Icon SVG Component
const EmailIcon = () => (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
)

export const AnimatedSignupCTA: React.FC<AnimatedSignupCTAProps> = ({
    title,
    subtitle,
    buttons,
    showUserAvatars = true,
}) => {
    // Generate random user avatars
    const generateRandomAvatars = () => {
        const genders = ['men', 'women']
        const avatars = []
        const usedNumbers = new Set()

        for (let i = 0; i < 5; i++) {
            const randomGender = genders[Math.floor(Math.random() * genders.length)]
            let randomNumber

            // Ensure we don't use the same number twice
            do {
                randomNumber = Math.floor(Math.random() * 99) + 1
            } while (usedNumbers.has(`${randomGender}-${randomNumber}`))

            usedNumbers.add(`${randomGender}-${randomNumber}`)
            avatars.push(`https://randomuser.me/api/portraits/${randomGender}/${randomNumber}.jpg`)
        }

        return avatars
    }

    const defaultAvatars = generateRandomAvatars()

    return (
        <div className="text-center space-y-5">
            {/* User Avatars */}
            {showUserAvatars && (
                <div className="relative inline-flex items-end justify-center w-full text-center mx-auto">
                    <img
                        src={defaultAvatars[0]}
                        className="absolute transform translate-x-24 ml-6 rounded-full w-12 h-12 md:w-16 md:h-16 border-4 border-white"
                        alt="User 1"
                    />
                    <img
                        src={defaultAvatars[1]}
                        className="absolute transform -translate-x-24 -ml-6 rounded-full w-12 h-12 md:w-16 md:h-16 border-4 border-white"
                        alt="User 2"
                    />
                    <img
                        src={defaultAvatars[2]}
                        className="absolute transform -translate-x-16 rounded-full w-16 h-16 md:w-20 md:h-20 border-4 border-white"
                        alt="User 3"
                    />
                    <img
                        src={defaultAvatars[3]}
                        className="absolute transform translate-x-16 rounded-full w-16 h-16 md:w-20 md:h-20 border-4 border-white"
                        alt="User 4"
                    />
                    <img
                        src={defaultAvatars[4]}
                        className="rounded-full w-20 h-20 md:w-24 md:h-24 border-4 border-white relative"
                        alt="User 5"
                    />
                </div>
            )}

            {/* Subtitle */}
            {subtitle && (
                <h2 className="text-base font-semibold tracking-wide uppercase">
                    {subtitle}
                </h2>
            )}

            {/* Main Title */}
            <p className="mt-1 text-2xl sm:text-3xl lg:text-4xl font-bold sm:tracking-tight">
                {title}
            </p>

            <br />

            {/* Buttons */}
            {buttons && buttons.length > 0 && (
                <div className="flex flex-col sm:flex-row space-y-2.5 sm:space-y-0 sm:space-x-2.5 items-center justify-center">
                    {buttons.map((button, i: number) => {
                        // Determine button variant and icon
                        let variant: "default" | "secondary" | "outline" | "link" = "default"
                        let startContent: React.ReactNode = null

                        if (button.style === 'default' || button.style === 'primary') {
                            variant = "default"
                        } else if (button.style === 'secondary') {
                            variant = "secondary"
                            if (button.icon === 'google') {
                                startContent = <GoogleIcon />
                            } else if (button.icon === 'email') {
                                startContent = <EmailIcon />
                            }
                        } else if (button.style === 'outline') {
                            variant = "outline"
                        } else if (button.style === 'link') {
                            variant = "link"
                        }

                        return (
                            <CMSLink
                                key={i}
                                className="w-full sm:w-auto"
                                type={button.type}
                                reference={button.reference}
                                url={button.url}
                            >
                                <Button
                                    variant={variant}
                                    size="lg"
                                    className="w-full text-base"
                                    startContent={startContent}
                                >
                                    {button.label}
                                </Button>
                            </CMSLink>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
