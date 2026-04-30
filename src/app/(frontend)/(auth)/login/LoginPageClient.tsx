"use client"

import React from "react"
import Link from "next/link"
import { Card } from "@heroui/react"
import { motion, AnimatePresence } from "framer-motion"
import { useLoginFlow } from "@/modules/auth"
import { Logo } from "@/components/Logo/Logo"
import { PoweredBy } from "@/components/PoweredBy/PoweredBy"
import { EmailStep } from "./components/EmailStep"
import { PasswordStep } from "./components/PasswordStep"
import { OtpPromptStep } from "./components/OtpPromptStep"

type LoginPageClientProps = {
    redirectTo: string
    allowNewUsers: boolean
}

export default function LoginPageClient({ redirectTo, allowNewUsers }: LoginPageClientProps) {
    const {
        step,
        email,
        password,
        error,
        isLoading,
        isSendingOtp,
        showPassword,
        setEmail,
        setPassword,
        setShowPassword,
        handleEmailSubmit,
        handlePasswordSubmit,
        handleSendOtp,
        handleEditEmail,
        handleGoogleLogin,
    } = useLoginFlow({ redirectTo })

    return (
        <div className="min-h-screen flex items-center justify-center md:px-4 py-12">
            <motion.div
                className="w-full md:max-w-[400px]"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
            >
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                >
                    <Card className="!bg-white !text-gray-900 shadow-2xl">
                        <Card.Header className="flex flex-col items-center gap-2 pt-8 pb-2">
                            <Logo forceLight width={180} height={100} />
                            <Card.Title className="text-xl font-semibold text-gray-900">
                                {step === "otp-prompt"
                                    ? "Verify your identity"
                                    : step === "email"
                                        ? "Sign in"
                                        : "Enter your password"
                                }
                            </Card.Title>
                            <Card.Description className="text-gray-600 text-sm text-center">
                                {step === "otp-prompt"
                                    ? "Confirm your account with a one-time code"
                                    : step === "email"
                                        ? "Use your email to continue"
                                        : "Welcome back"
                                }
                            </Card.Description>
                        </Card.Header>

                        <Card.Content>
                            <AnimatePresence mode="wait">
                                {step === "email" ? (
                                    <EmailStep
                                        email={email}
                                        error={error}
                                        isLoading={isLoading}
                                        onEmailChange={setEmail}
                                        onSubmit={handleEmailSubmit}
                                        onGoogleLogin={handleGoogleLogin}
                                    />
                                ) : step === "password" ? (
                                    <PasswordStep
                                        email={email}
                                        password={password}
                                        error={error}
                                        isLoading={isLoading}
                                        showPassword={showPassword}
                                        onPasswordChange={setPassword}
                                        onToggleShowPassword={() => setShowPassword(!showPassword)}
                                        onEditEmail={handleEditEmail}
                                        onSubmit={handlePasswordSubmit}
                                    />
                                ) : (
                                    <OtpPromptStep
                                        email={email}
                                        error={error}
                                        isSendingOtp={isSendingOtp}
                                        onEditEmail={handleEditEmail}
                                        onSendOtp={handleSendOtp}
                                    />
                                )}
                            </AnimatePresence>
                        </Card.Content>

                        {allowNewUsers && (
                            <Card.Footer className="justify-center pb-6">
                                <p className="text-center text-gray-600 text-sm">
                                    Don't have an account?{" "}
                                    <Link href="/signup" className="text-gray-900 font-medium hover:underline">
                                        Sign up
                                    </Link>
                                </p>
                            </Card.Footer>
                        )}
                    </Card>
                    <PoweredBy />
                </motion.div>
            </motion.div>
        </div>
    )
}
