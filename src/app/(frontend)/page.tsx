import { redirect } from 'next/navigation'

// Unauthenticated users land here (proxy already sends authenticated users to /portafolio).
// Send them directly to the admin login so they can authenticate.
export default function FrontendHomePage() {
	redirect('/admin/login?redirect=%2Fportafolio')
}
