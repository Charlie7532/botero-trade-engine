"use client"

import React from "react"
import { Button, Form, Input, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"

interface EmailStepProps {
    email: string
    error: string | null
    isLoading: boolean
    onEmailChange: (value: string) => void
    onSubmit: (e: React.FormEvent<HTMLFormElement>) => void
    onGoogleLogin: () => void
}

/**
 * Login Step 1 — Email Entry
 *
 * Presentational component for the initial email input and Google login button.
 * Receives all data and callbacks via props.
 */
export function EmailStep({
    email,
    error,
    isLoading,
    onEmailChange,
    onSubmit,
    onGoogleLogin,
}: EmailStepProps) {
    return (
        <motion.div
            key="email-step"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.3 }}
        >
            {/* Google Button */}
            <Button
                fullWidth
                variant="outline"
                size="lg"
                className="mb-4 h-12 rounded-full border-gray-300 text-gray-700 hover:bg-gray-50"
                onPress={onGoogleLogin}
            >
                <Icon icon="flat-color-icons:google" width={20} />
                Continue with Google
            </Button>

            {/* Divider */}
            <div className="flex items-center gap-4 my-4">
                <hr className="flex-1 bg-gray-200 border-0 h-px" />
                <span className="text-gray-500 text-sm">or</span>
                <hr className="flex-1 bg-gray-200 border-0 h-px" />
            </div>

            {/* Email Form */}
            <Form onSubmit={onSubmit} className="flex flex-col gap-4">
                {error && (
                    <motion.div
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

                <Input
                    required
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    type="email"
                    name="email"
                    aria-label="Email"
                    placeholder="Email"
                    variant="secondary"
                    className="h-12 w-full rounded-full bg-white border border-gray-300 px-4"
                />

                <Button
                    type="submit"
                    fullWidth
                    size="lg"
                    className="h-12 font-semibold rounded-full"
                    variant="primary"
                    isPending={isLoading}
                >
                    {({ isPending }) => (
                        <>
                            {isPending ? <Spinner color="current" size="sm" /> : null}
                            {isPending ? "Loading..." : "Continue"}
                        </>
                    )}
                </Button>
            </Form>
        </motion.div>
    )
}
