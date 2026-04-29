"use client"

import React from "react"
import { Button, Alert } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"

interface OtpPromptStepProps {
    email: string
    error: string | null
    isSendingOtp: boolean
    onEditEmail: () => void
    onSendOtp: () => void
}

/**
 * Login Step 2b — OTP Prompt
 *
 * Presentational component shown for migrated users who don't have a password.
 * Displays info about identity verification and a button to send the OTP code.
 */
export function OtpPromptStep({
    email,
    error,
    isSendingOtp,
    onEditEmail,
    onSendOtp,
}: OtpPromptStepProps) {
    return (
        <motion.div
            key="otp-prompt-step"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
        >
            {/* Email Display */}
            <div className="flex items-center justify-between border border-gray-300 rounded-xl px-4 py-3 mb-4">
                <span className="text-gray-900 text-sm">{email}</span>
                <button
                    type="button"
                    onClick={onEditEmail}
                    className="text-gray-600 text-sm font-medium hover:text-gray-900"
                >
                    Edit
                </button>
            </div>

            {error && (
                <motion.div
                    className="mb-4"
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

            {/* Info Box */}
            <Alert status="accent" className="mb-4">
                <Alert.Indicator>
                    <Icon icon="lucide:mail" width={20} />
                </Alert.Indicator>
                <Alert.Content>
                    <Alert.Description>
                        We need to verify your identity before signing you in. We will send a one-time code to your email.
                    </Alert.Description>
                </Alert.Content>
            </Alert>

            <Button
                fullWidth
                size="lg"
                variant="primary"
                isPending={isSendingOtp}
                onPress={onSendOtp}
            >
                {isSendingOtp ? 'Sending code...' : 'Send code'}
            </Button>
        </motion.div>
    )
}
