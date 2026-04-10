'use client'

import React from 'react'

interface HamburgerButtonProps {
    isOpen: boolean
    onClick: () => void
    className?: string
}

export const HamburgerButton: React.FC<HamburgerButtonProps> = ({
    isOpen,
    onClick,
    className = ''
}) => {
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
        onClick()
        // Remove focus after click
        e.currentTarget.blur()
    }

    return (
        <button
            onClick={handleClick}
            className={`md:hidden flex flex-col justify-center items-center w-8 h-8 space-y-1 focus:outline-none rounded ${className}`}
            aria-label={isOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={isOpen}
        >
            {/* Top line */}
            <span
                className={`block w-6 h-0.5 bg-gray-700 dark:bg-gray-300 transition-all duration-300 ease-in-out transform origin-center ${isOpen
                    ? 'rotate-45 translate-y-1.5'
                    : 'rotate-0 translate-y-0'
                    }`}
            />

            {/* Middle line */}
            <span
                className={`block w-6 h-0.5 bg-gray-700 dark:bg-gray-300 transition-all duration-300 ease-in-out ${isOpen ? 'opacity-0 scale-0' : 'opacity-100 scale-100'
                    }`}
            />

            {/* Bottom line */}
            <span
                className={`block w-6 h-0.5 bg-gray-700 dark:bg-gray-300 transition-all duration-300 ease-in-out transform origin-center ${isOpen
                    ? '-rotate-45 -translate-y-1.5'
                    : 'rotate-0 translate-y-0'
                    }`}
            />
        </button>
    )
}