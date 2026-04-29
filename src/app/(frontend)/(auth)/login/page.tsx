"use client"

import React, { Suspense } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { Card, Spinner } from "@heroui/react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslations } from "next-intl"
import { useLoginFlow } from "@/modules/auth"
import { Logo } from "@/components/Logo/Logo"
import { PoweredBy } from "@/components/PoweredBy"
import { EmailStep } from "./components/EmailStep"
import { PasswordStep } from "./components/PasswordStep"
import { OtpPromptStep } from "./components/OtpPromptStep"

function LoginContent() {
    const t = useTranslations("Auth.login")
    const searchParams = useSearchParams()

    // Get redirect URL from query params (e.g., from admin login)
    const redirectTo = searchParams.get('redirect') || '/account'

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
                    <Card>
                        <Card.Header className="flex flex-col items-center gap-2 pt-8 pb-2">
                            {/* Logo */}
                            <Logo forceLight width={180} height={100} />
                            <Card.Title className="text-xl font-semibold text-gray-900">
                                {step === "otp-prompt"
                                    ? t("verifyIdentity")
                                    : step === "email"
                                        ? t("title")
                                        : t("enterPassword")
                                }
                            </Card.Title>
                            <Card.Description className="text-gray-600 text-sm text-center">
                                {step === "otp-prompt"
                                    ? t("verifyIdentitySubtitle")
                                    : step === "email"
                                        ? t("subtitle")
                                        : t("enterPasswordSubtitle")
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
                                        onSubmit={(e) => handleEmailSubmit(e, t)}
                                        onGoogleLogin={handleGoogleLogin}
                                        t={t}
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
                                        onSubmit={(e) => handlePasswordSubmit(e, t)}
                                        t={t}
                                    />
                                ) : (
                                    <OtpPromptStep
                                        email={email}
                                        error={error}
                                        isSendingOtp={isSendingOtp}
                                        onEditEmail={handleEditEmail}
                                        onSendOtp={() => handleSendOtp(t)}
                                        t={t}
                                    />
                                )}
                            </AnimatePresence>
                        </Card.Content>

                        <Card.Footer className="justify-center pb-6">
                            {/* Sign up link */}
                            <p className="text-center text-gray-600 text-sm">
                                {t("noAccount")}{" "}
                                <Link href="/signup" className="text-gray-900 font-medium hover:underline">
                                    {t("signUp")}
                                </Link>
                            </p>
                        </Card.Footer>
                    </Card>
                    <PoweredBy />
                </motion.div>
            </motion.div>
        </div>
    )
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center px-4 py-12">
                <Spinner size="lg" color="accent" />
            </div>
        }>
            <LoginContent />
        </Suspense>
    )
}
