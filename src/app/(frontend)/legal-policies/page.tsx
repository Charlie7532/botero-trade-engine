import React from 'react'
import Link from 'next/link'
import { getCachedSiteSettings } from '@/utilities/getSiteSettings'
import { CMSLink } from '@/components/Link'

export const dynamic = 'force-dynamic'

export default async function LegalPoliciesPage() {
    const siteSettings = await getCachedSiteSettings(1)()
    const policies = siteSettings?.legalPolicies || []

    return (
        <main className="max-w-4xl mx-auto py-12 px-6 min-h-screen">
            <h1 className="text-3xl font-semibold mb-6">Legal Policies</h1>

            {policies.length === 0 && (
                <p className="text-gray-500">No legal policies configured. Add them in the Site Settings.</p>
            )}

            <ul className="space-y-4">
                {policies.map((policy: any, idx: number) => (
                    <li key={idx}>
                        {/* Use CMSLink to respect internal/external behavior */}
                        <CMSLink {...{
                            ...policy,
                            label: policy.label || policy.name,
                        }} className="text-blue-500 hover:underline" />
                    </li>
                ))}
            </ul>

            <div className="mt-8">
                <Link href="/">Back to home</Link>
            </div>
        </main>
    )
}
