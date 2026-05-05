"use client"

import React from "react"
import Link from "next/link"
import { Button, Card, Form, Input, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"
import { useForgotPasswordFlow } from "@/modules/auth"
import { Logo } from "@/components/Logo/Logo"
import { PoweredBy } from "@/components/PoweredBy/PoweredBy"

export default function ForgotPasswordPage() {
    const {
        email,
        error,
        isLoading,
        setEmail,
        handleSubmit,
    } = useForgotPasswordFlow()

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
                                Forgot your password?
                            </Card.Title>
                            <Card.Description className="text-gray-600 text-sm text-center">
                                Enter your email and we will send a verification code.
                            </Card.Description>
                        </Card.Header>

                        <Card.Content>
                            <Form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
                                    onChange={(e) => setEmail(e.target.value)}
                                    type="email"
                                    name="email"
                                    aria-label="Email"
                                    placeholder="Email"
                                    className="h-12 w-full bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400 rounded-lg transition-all text-base text-gray-900 px-4"
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
                                            {isPending ? "Sending..." : "Send reset code"}
                                        </>
                                    )}
                                </Button>

                                <div className="text-center">
                                    <Link
                                        href="/login"
                                        className="text-sm text-gray-600 hover:text-gray-900 inline-flex items-center gap-1"
                                    >
                                        <Icon icon="lucide:arrow-left" width={16} />
                                        Back to login
                                    </Link>
                                </div>
                            </Form>
                        </Card.Content>
                    </Card>
                    <PoweredBy />
                </motion.div>
            </motion.div>
        </div>
    )
}
