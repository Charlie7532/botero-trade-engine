"use client"

import React, { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { Button, Card, Form, TextField, Input, Label, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"
import { useTranslations } from "next-intl"
import { useAuth } from "@/providers/Auth"
import { PoweredBy } from "@/components/PoweredBy"
import { Logo } from "@/components/Logo/Logo"

export default function SignupPage() {
    const t = useTranslations("Auth.signup")
    const router = useRouter()
    const { create } = useAuth()

    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [confirmPassword, setConfirmPassword] = useState("")
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [showPassword, setShowPassword] = useState(false)
    const [showConfirmPassword, setShowConfirmPassword] = useState(false)

    const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setIsLoading(true)
        setError(null)

        if (password !== confirmPassword) {
            setError(t("passwordMismatch"))
            setIsLoading(false)
            return
        }

        try {
            await create({ email, password, passwordConfirm: confirmPassword })
            router.push("/")
        } catch (err) {
            setError(t("error"))
        } finally {
            setIsLoading(false)
        }
    }

    const handleGoogleSignup = () => {
        // Google OAuth will be implemented later
        console.log("Google signup - to be implemented")
    }

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
                                {t("title")}
                            </Card.Title>
                            <Card.Description className="text-gray-500 text-sm text-center">
                                {t("subtitle")}
                            </Card.Description>
                        </Card.Header>

                        <Card.Content>
                            {/* Google Button */}
                            <Button
                                fullWidth
                                variant="outline"
                                size="lg"
                                className="mb-4 h-12 border-gray-300 text-gray-700 hover:bg-gray-50"
                                onPress={handleGoogleSignup}
                            >
                                <Icon icon="flat-color-icons:google" width={20} />
                                {t("continueWithGoogle")}
                            </Button>

                            {/* Divider */}
                            <div className="flex items-center gap-4 my-4">
                                <hr className="flex-1 bg-gray-200 border-0 h-px" />
                                <span className="text-gray-500 text-sm">{t("orContinueWith")}</span>
                                <hr className="flex-1 bg-gray-200 border-0 h-px" />
                            </div>

                            {/* Signup Form */}
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
                                    aria-label={t("email")}
                                    placeholder={t("email")}
                                    className="h-12 w-full bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400 rounded-lg transition-all text-base text-gray-900 px-4"
                                />

                                <div className="relative w-full">
                                    <Input
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        type={showPassword ? "text" : "password"}
                                        name="password"
                                        aria-label={t("password")}
                                        placeholder={t("password")}
                                        className="h-12 w-full bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400 rounded-lg transition-all text-base text-gray-900 px-4 pr-12"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 focus:outline-none"
                                    >
                                        <Icon
                                            icon={showPassword ? "lucide:eye-off" : "lucide:eye"}
                                            className="text-gray-400"
                                            width={20}
                                        />
                                    </button>
                                </div>

                                <div className="relative w-full">
                                    <Input
                                        required
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        type={showConfirmPassword ? "text" : "password"}
                                        name="confirmPassword"
                                        aria-label={t("confirmPassword")}
                                        placeholder={t("confirmPassword")}
                                        className="h-12 w-full bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400 rounded-lg transition-all text-base text-gray-900 px-4 pr-12"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 focus:outline-none"
                                    >
                                        <Icon
                                            icon={showConfirmPassword ? "lucide:eye-off" : "lucide:eye"}
                                            className="text-gray-400 hover:text-gray-600 transition-colors"
                                            width={20}
                                        />
                                    </button>
                                </div>

                                {/* Terms Agreement */}
                                <p className="text-xs text-gray-600 text-center">
                                    {t("termsAgreement")}{" "}
                                    <Link href="/terms" className="text-gray-900 hover:underline">
                                        {t("termsOfService")}
                                    </Link>{" "}
                                    {t("and")}{" "}
                                    <Link href="/privacy" className="text-gray-900 hover:underline">
                                        {t("privacyPolicy")}
                                    </Link>
                                </p>

                                <Button
                                    type="submit"
                                    fullWidth
                                    size="lg"
                                    className="h-12 font-semibold rounded-full text-gray-900 data-[loading=true]:text-gray-900"
                                    variant="primary"
                                    isPending={isLoading}
                                >
                                    {({ isPending }) => (
                                        <>
                                            {isPending ? <Spinner color="current" size="sm" /> : null}
                                            {isPending ? t("loading") : t("createAccount")}
                                        </>
                                    )}
                                </Button>
                            </Form>
                        </Card.Content>

                        <Card.Footer className="justify-center pb-6">
                            {/* Sign in link */}
                            <p className="text-center text-gray-600 text-sm">
                                {t("hasAccount")}{" "}
                                <Link href="/login" className="text-gray-900 font-medium hover:underline">
                                    {t("signIn")}
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
