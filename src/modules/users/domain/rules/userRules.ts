/**
 * Pure rule to determine if the current user being created is the very first user in the database.
 */
export function isFirstUser(totalDocs: number): boolean {
  return totalDocs === 0
}

/**
 * Pure rule to determine if the requested role requires an automatic upgrade to superadmin
 * (usually evaluated when handling the first system user).
 */
export function requiresSuperAdminRole(currentRole?: string): boolean {
  return currentRole !== 'admin' && currentRole !== 'superadmin'
}
