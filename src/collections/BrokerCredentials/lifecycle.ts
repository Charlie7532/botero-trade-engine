import { handleBeforeChangeHook } from '@/shared/handlers'
import { encryptCredential } from './domain/useCases/encryptCredential'
import { maskCredentialValue } from './domain/rules/credentialRules'

const encryptPlaintextValue = handleBeforeChangeHook({
  name: 'BrokerCredentials',
  operation: 'all',
  handler: async ({ data }) => {
    const plaintext = data.plaintextValue

    if (!plaintext) {
      delete data.plaintextValue
      return data
    }

    const encryptionSecret = process.env.BROKER_CREDENTIAL_ENCRYPTION_KEY
    if (!encryptionSecret) {
      throw new Error(
        'BROKER_CREDENTIAL_ENCRYPTION_KEY environment variable is not set.',
      )
    }

    const encrypted = encryptCredential(plaintext, encryptionSecret)

    data.encryptedValue = encrypted.ciphertext
    data.iv = encrypted.iv
    data.authTag = encrypted.authTag
    data.maskedPreview = maskCredentialValue(plaintext)

    delete data.plaintextValue

    return data
  },
})

export const brokerCredentialsLifecycle = {
  beforeChange: [encryptPlaintextValue],
}
