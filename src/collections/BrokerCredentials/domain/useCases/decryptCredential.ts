import { decryptValue } from '@/shared/domain/encryption'
import type { EncryptedPayload } from '@/shared/domain/encryption'

export function decryptCredential(
  encryptedPayload: EncryptedPayload,
  encryptionSecret: string,
): string {
  return decryptValue(encryptedPayload, encryptionSecret)
}
