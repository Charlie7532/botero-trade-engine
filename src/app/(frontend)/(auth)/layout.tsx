
export default function Layout({ children }: { children: React.ReactNode }) {
    return (
        <main id="auth" className="flex flex-col min-h-screen bg-white md:bg-accent">
            {children}
        </main>
    )
}