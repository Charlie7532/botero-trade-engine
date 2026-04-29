"use client"

import React, { Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { Button, Card, Form, Input, Alert, Spinner } from "@heroui/react"
import { Icon } from "@iconify/react"
import { motion } from "framer-motion"
import { useTranslations } from "next-intl"
import { useSetPasswordFlow } from "@/modules/auth"
import { Logo } from "@/components/Logo/Logo"
import { PoweredBy } from "@/components/PoweredBy"

function SetPasswordContent() {
    const t = useTranslations("Auth.setPassword")
    const searchParams = useSearchParams()
    const redirectTo = searchParams.get('redirect') || '/'

    const {
        password,
        confirmPassword,
        error,
        isLoading,
        showPassword,
        showConfirmPassword,
        strength,
        passwordsMatch,
        getStrengthDisplay,
        setPassword,
        setConfirmPassword,
        setShowPassword,
        setShowConfirmPassword,
        handleSubmit,
        handleSkip,
    } = useSetPasswordFlow({ redirectTo })

    const strengthDisplay = getStrengthDisplay(t)

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
                                {t("title")}
                            </Card.Title>
                            <Card.Description className="text-gray-600 text-sm text-center">
                                {t("subtitle")}
                            </Card.Description>
                        </Card.Header>

                        <Card.Content>
                            {/* Error Message */}
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

                            {/* Form */}
                            <Form onSubmit={(e) => handleSubmit(e, t)} className="flex flex-col gap-4">
                                <div className="relative w-full">
                                    <Input
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
                                            className="text-gray-400 hover:text-gray-600 transition-colors"
                                            width={20}
                                        />
                                    </button>
                                </div>

                                <div className="relative w-full">
                                    <Input
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

                                {confirmPassword && !passwordsMatch && (
                                    <p className="text-red-500 text-xs px-1">
                                        {t("passwordsMismatch")}
                                    </p>
                                )}

                                {/* Password Strength Indicator */}
                                {password.length > 0 && (
                                    <div className="px-1">
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="text-xs text-gray-500">{t("passwordStrength")}</span>
                                            <span className={`text-xs font-medium ${strengthDisplay.label === t("strength.weak") ? "text-red-500" :
                                                strengthDisplay.label === t("strength.medium") ? "text-yellow-600" :
                                                    "text-green-600"
                                                }`}>
                                                {strengthDisplay.label}
                                            </span>
                                        </div>
                                        <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                            <div
                                                className={`h-full ${strengthDisplay.color} transition-all duration-300`}
                                                style={{ width: strengthDisplay.width }}
                                            />
                                        </div>
                                    </div>
                                )}

                                {/* Password Recommendations */}
                                <div className="space-y-1 px-1">
                                    <p className="text-xs text-gray-500 mb-2">{t("recommendations")}</p>
                                    <RequirementItem met={strength.hasMinLength} text={t("requirements.minLength")} />
                                    <RequirementItem met={strength.hasUppercase} text={t("requirements.uppercase")} />
                                    <RequirementItem met={strength.hasNumber} text={t("requirements.number")} />
                                    <RequirementItem met={strength.hasSpecialChar} text={t("requirements.specialChar")} />
                                    <p className="text-xs text-gray-400 mt-2 italic">{t("minimumCriteria")}</p>
                                </div>

                                <Button
                                    type="submit"
                                    fullWidth
                                    size="lg"
                                    className="h-12 font-semibold rounded-full text-gray-900 data-[loading=true]:text-gray-900"
                                    variant="primary"
                                    isPending={isLoading}
                                    isDisabled={!!confirmPassword && !passwordsMatch}
                                >
                                    {({ isPending }) => (
                                        <>
                                            {isPending ? <Spinner color="current" size="sm" /> : null}
                                            {isPending ? t("setting") : t("setPassword")}
                                        </>
                                    )}
                                </Button>
                            </Form>
                        </Card.Content>

                        <Card.Footer className="justify-center pb-6">
                            {/* Skip Link */}
                            <button
                                onClick={handleSkip}
                                className="text-gray-600 text-sm hover:text-gray-900"
                            >
                                {t("skipForNow")}
                            </button>
                        </Card.Footer>
                    </Card>
                    <PoweredBy />
                </motion.div>
            </motion.div>
        </div>
    )
}

function RequirementItem({ met, text }: { met: boolean; text: string }) {
    return (
        <div className="flex items-center gap-2 text-xs">
            <Icon
                icon={met ? "lucide:check-circle" : "lucide:circle"}
                className={met ? "text-green-500" : "text-gray-300"}
                width={14}
            />
            <span className={met ? "text-gray-700" : "text-gray-400"}>
                {text}
            </span>
        </div>
    )
}

export default function SetPasswordPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center px-4 py-12">
                <Spinner size="lg" color="accent" />
            </div>
        }>
            <SetPasswordContent />
        </Suspense>
    )
}
