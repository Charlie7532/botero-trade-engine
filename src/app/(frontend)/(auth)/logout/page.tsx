"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Spinner } from "@heroui/react"
import { useAuth } from "@/providers/Auth"

export default function LogoutPage() {
    const router = useRouter()
    const { logout } = useAuth()

    useEffect(() => {
        const performLogout = async () => {
            try {
                await logout()
            } catch (error) {
                console.error("Logout error:", error)
            } finally {
                router.push("/")
            }
        }

        performLogout()
    }, [logout, router])

    return (
        <div className="min-h-screen flex items-center justify-center">
            <Spinner size="lg" />
        </div>
    )
}
