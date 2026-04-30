import React from 'react'
import Image from 'next/image'
import Link from 'next/link'

interface PoweredByProps {
    className?: string;
    width?: number;
    height?: number;
}

export const PoweredBy: React.FC<PoweredByProps> = ({
    className = '',
    width = 28,
    height = 28
}) => {
    return (
        <div className={`mt-4 w-full flex justify-center hover:opacity-80 transition-all duration-300 ${className}`}>
            <Link
                href="https://main12.com"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center"
            >
                <Image
                    src="/assets/logos/power_by_brand.ico"
                    alt="Powered by Main12"
                    width={width}
                    height={height}
                    className="object-contain"
                />
            </Link>
        </div>
    )
}
