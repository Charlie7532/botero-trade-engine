import { isFirstUser, requiresSuperAdminRole } from '../rules/userRules'

/**
 * Use case to assign the initial admin role to a user.
 * Assures that the very first user in a new database is privileged.
 * Contains purely business logic, decoupled from Payload or active requests.
 */
export function assignInitialAdminRole<T extends { role?: string }>(
  userData: T,
  totalUsersInDatabase: number,
): T {
  if (!isFirstUser(totalUsersInDatabase)) {
    return userData
  }

  if (requiresSuperAdminRole(userData?.role)) {
    return {
      ...userData,
      role: 'superadmin',
    }
  }

  return userData
}
