"use client"

import React, { Suspense } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { Button, Card, InputOTP, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"
import { useVerifyOtpFlow } from "@/modules/auth"
import { Logo } from "@/components/Logo/Logo"
import { PoweredBy } from "@/components/PoweredBy/PoweredBy"

function VerifyOtpContent() {
    const searchParams = useSearchParams()
    const email = searchParams.get("email") || ""
    const purpose = searchParams.get("purpose") || "login"
    const redirectTo = searchParams.get("redirect") || "/"

    const {
        otp,
        error,
        isLoading,
        isResending,
        resendCooldown,
        setOtp,
        handleSubmit,
        handleComplete,
        handleResendCode,
    } = useVerifyOtpFlow({ email, purpose, redirectTo })

    if (!email) {
        return null
    }

    return (
        <div className="min-h-screen flex items-center justify-center px-4 py-12">
            <motion.div
                className="w-full max-w-[400px]"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
            >
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                >
                    <Card className="bg-white shadow-2xl">
                        <Card.Header className="flex flex-col items-center gap-2 pt-8 pb-2">
                            {/* Logo */}
                            <Logo forceLight width={180} height={100} />
                            <Card.Title className="text-xl font-semibold text-gray-900">
                                {purpose === "password-reset" ? "Reset your password" : "Verify your identity"}
                            </Card.Title>
                            <Card.Description className="text-gray-500 text-sm text-center">
                                {purpose === "password-reset"
                                    ? "Enter the code we sent to continue resetting your password."
                                    : "Enter the code we sent to your email to sign in."}
                            </Card.Description>
                            <p className="text-gray-700 text-sm font-medium mt-1">
                                {email}
                            </p>
                        </Card.Header>

                        <Card.Content className="flex flex-col items-center gap-4">
                            {/* OTP Input - HeroUI v3 InputOTP */}
                            <InputOTP
                                maxLength={6}
                                value={otp}
                                onChange={setOtp}
                                onComplete={handleComplete}
                                isDisabled={isLoading}
                                isInvalid={!!error}
                                autoFocus
                                variant="secondary"
                            >
                                <InputOTP.Group>
                                    <InputOTP.Slot index={0} />
                                    <InputOTP.Slot index={1} />
                                    <InputOTP.Slot index={2} />
                                </InputOTP.Group>
                                <InputOTP.Separator />
                                <InputOTP.Group>
                                    <InputOTP.Slot index={3} />
                                    <InputOTP.Slot index={4} />
                                    <InputOTP.Slot index={5} />
                                </InputOTP.Group>
                            </InputOTP>

                            {/* Error Message */}
                            {error && (
                                <motion.div
                                    className="w-full"
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: "auto" }}
                                >
                                    <Alert status="danger">
                                        <Alert.Content>
                                            <Alert.Description>{error}</Alert.Description>
                                        </Alert.Content>
                                    </Alert>
                                </motion.div>
                            )}

                            <Button
                                fullWidth
                                size="lg"
                                className="h-12 font-semibold rounded-full"
                                variant="primary"
                                isPending={isLoading}
                                onPress={() => handleSubmit(otp)}
                                isDisabled={otp.length !== 6 || isLoading}
                            >
                                {({ isPending }) => (
                                    <>
                                        {isPending ? <Spinner color="current" size="sm" /> : null}
                                        {isPending ? "Verifying..." : "Verify"}
                                    </>
                                )}
                            </Button>

                            {/* Resend Code */}
                            <div className="text-center">
                                <p className="text-gray-600 text-sm mb-2">
                                    Didn't receive a code?
                                </p>
                                <button
                                    onClick={handleResendCode}
                                    disabled={isResending || resendCooldown > 0}
                                    className="text-primary font-medium text-sm hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {isResending ? (
                                        <span className="flex items-center justify-center gap-2">
                                            <Icon icon="lucide:loader-2" className="animate-spin" width={16} />
                                            Sending...
                                        </span>
                                    ) : resendCooldown > 0 ? (
                                        `Resend in ${resendCooldown}s`
                                    ) : (
                                        "Resend code"
                                    )}
                                </button>
                            </div>
                        </Card.Content>

                        <Card.Footer className="justify-center pb-6 pt-2 border-t border-gray-100">
                            {/* Back to Login */}
                            <Link
                                href="/login"
                                className="text-gray-600 text-sm hover:text-gray-900 flex items-center justify-center gap-1"
                            >
                                <Icon icon="lucide:arrow-left" width={16} />
                                Back to login
                            </Link>
                        </Card.Footer>
                    </Card>
                    <PoweredBy />
                </motion.div>
            </motion.div>
        </div>
    )
}

export default function VerifyOtpPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center px-4 py-12">
                <Spinner size="lg" color="accent" />
            </div>
        }>
            <VerifyOtpContent />
        </Suspense>
    )
}
