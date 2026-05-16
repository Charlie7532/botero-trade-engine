
import ForceLightTheme from './ForceLightTheme'

export default function Layout({ children }: { children: React.ReactNode }) {
    return (
        <main id="auth" data-theme="light" className="light flex flex-col min-h-screen bg-white md:bg-accent">
            <ForceLightTheme />
            {children}
        </main>
    )
}