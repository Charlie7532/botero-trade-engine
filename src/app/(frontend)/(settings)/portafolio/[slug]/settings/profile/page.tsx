import type { UserAvatar } from '@/payload-types'
import { getMeUser } from '@/utilities/getMeUser'
import ProfileForm from './ProfileForm'

export default async function ProfileSettingsPage() {
  const { user } = await getMeUser({
    nullUserRedirect: '/admin/login?redirect=%2Fportafolio',
  })

  const avatar = user.avatar as UserAvatar | null | undefined
  const avatarUrl = avatar?.url ?? null

  return (
    <div>
      <header className="mb-8">
        <p className="text-[11px] font-semibold tracking-widest uppercase text-muted">Profile</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Personal information
        </h1>
        <p className="mt-1.5 text-sm text-muted">Update your name, nickname, and profile photo.</p>
      </header>

      <section className="rounded-2xl border border-border bg-surface p-6">
        <ProfileForm
          userId={user.id}
          name={user.name}
          nickname={user.nickname}
          preferredLanguage={user.preferredLanguage}
          email={user.email}
          avatarUrl={avatarUrl}
        />
      </section>
    </div>
  )
}
