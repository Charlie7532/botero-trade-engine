import { encryptValue } from '@/shared/domain/encryption'
import type { EncryptedPayload } from '@/shared/domain/encryption'

export function encryptCredential(
  plaintextValue: string,
  encryptionSecret: string,
): EncryptedPayload {
  return encryptValue(plaintextValue, encryptionSecret)
}
