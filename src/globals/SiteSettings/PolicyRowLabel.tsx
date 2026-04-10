'use client'
import React from 'react'
import { RowLabelProps, useRowLabel } from '@payloadcms/ui'

type PolicyItem = {
    name?: string | null
    label?: string | null
    type?: 'reference' | 'custom'
}

export const PolicyRowLabel: React.FC<RowLabelProps> = () => {
    const data = useRowLabel<PolicyItem>()
    const name = data?.data?.name || `Policy ${data?.rowNumber !== undefined ? (data.rowNumber + 1).toString().padStart(2, '0') : ''}`

    return (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v13a0 0 0 0 1 0 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M14 3v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span style={{ fontSize: 13, lineHeight: '14px' }}>{name}</span>
        </div>
    )
}
