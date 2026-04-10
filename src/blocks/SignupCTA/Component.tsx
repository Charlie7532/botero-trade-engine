import type React from "react"

import { AnimatedSignupCTA } from './Component.client'

type SignupCTAProps = {
  title: string
  subtitle?: string | null
  buttons?:
  | {
    type?: ("reference" | "custom") | null
    reference?: {
      relationTo: "pages"
      value: number | any
    } | null
    url?: string | null
    label: string
    style?: ("primary" | "secondary" | "outline") | null
    icon?: ("none" | "google" | "email") | null
    id?: string | null
  }[]
  | null
  showUserAvatars?: boolean | null
  id?: string | null
  blockName?: string | null
  blockType: "signupCTA"
}

export const SignupCTA: React.FC<SignupCTAProps> = (props) => {
  return (
    <section className="w-full flex">
      <div className="max-w-7xl mx-auto py-16 px-4 sm:py-24 sm:px-6 lg:px-8">
        <AnimatedSignupCTA {...props} />
      </div>
    </section>
  )
}
