"use client"

import React from "react"
import Link from "next/link"
import { Button, Form, Input, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"

interface PasswordStepProps {
    email: string
    password: string
    error: string | null
    isLoading: boolean
    showPassword: boolean
    onPasswordChange: (value: string) => void
    onToggleShowPassword: () => void
    onEditEmail: () => void
    onSubmit: (e: React.FormEvent<HTMLFormElement>) => void
}

/**
 * Login Step 2a — Password Entry
 *
 * Presentational component shown when the user has a password set.
 * Displays the email with an edit button, password field, and forgot password link.
 */
export function PasswordStep({
    email,
    password,
    error,
    isLoading,
    showPassword,
    onPasswordChange,
    onToggleShowPassword,
    onEditEmail,
    onSubmit,
}: PasswordStepProps) {
    return (
        <motion.div
            key="password-step"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
        >
            {/* Email Display - with Edit button */}
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

            {/* Password Form */}
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

                <div className="relative w-full">
                    <Input
                        required
                        value={password}
                        onChange={(e) => onPasswordChange(e.target.value)}
                        type={showPassword ? "text" : "password"}
                        name="password"
                        autoFocus
                        aria-label="Password"
                        placeholder="Password"
                        className="h-12 w-full bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400 rounded-lg transition-all text-base text-gray-900 px-4 pr-12"
                    />
                    <button
                        type="button"
                        onClick={onToggleShowPassword}
                        className="absolute right-4 top-1/2 -translate-y-1/2 focus:outline-none"
                    >
                        <Icon
                            icon={showPassword ? "lucide:eye-off" : "lucide:eye"}
                            className="text-gray-400 hover:text-gray-600 transition-colors"
                            width={20}
                        />
                    </button>
                </div>

                <div className="text-left">
                    <Link
                        href="/forgot-password"
                        className="text-sm text-gray-700 hover:text-gray-900 hover:underline"
                    >
                        Forgot password?
                    </Link>
                </div>

                <Button
                    type="submit"
                    fullWidth
                    size="lg"
                    className="h-12 font-semibold text-gray-900 data-[loading=true]:text-gray-900"
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
