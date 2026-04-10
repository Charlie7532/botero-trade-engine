import Link from 'next/link';

interface HeroBlockProps {
    title: string;
    highlightedText: string;
    secondaryTitle: string;
    description: string
    href: string;
    ButtonText: string;
    className?: string;
}
const HeroBlock = ({ title, highlightedText, secondaryTitle, description, href, ButtonText, className }: HeroBlockProps) => {

    return (
        <div className={className}>
            <div className="relative w-fit group tracking-tight" style={{ maxWidth: "650px" }}>
                <h1 className={`text-3xl md:text-6xl font-bold leading-tight text-left`}>
                    {title}
                    <span className="relative inline-block">
                        <span className="relative z-10">
                            {highlightedText}
                        </span>
                        <div className="rounded-full px-6 absolute inset-x-0 bottom-0 h-3 bg-primary opacity-90 z-0 transition-all duration-500 group-hover:h-8" />
                    </span>
                    {secondaryTitle}
                </h1>
            </div>

            <p className="w-full mt-5 text-left" style={{ fontSize: "1.2rem", maxWidth: "500px" }}>
                {description}
            </p>
            <br />
            <div className="flex mt-5 gap-3 justify-start">
                <Link
                    className="bg-primary text-primary-foreground px-12 py-6 rounded-full text-lg font-semibold shadow-lg hover:shadow-xl transition-all duration-300"
                    href={href}
                >
                    {ButtonText}
                </Link>
            </div>
        </div>
    )
}

export default HeroBlock