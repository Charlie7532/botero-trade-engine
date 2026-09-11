import crypto from 'crypto'

import { handleAfterChangeHook, handleBeforeChangeHook } from '@/shared/handlers'
import { encryptCredential } from './domain/useCases/encryptCredential'
import { syncVaultOnSave } from './infrastructure/hooks/syncVaultOnSave'
import {
  BROKER_CREDENTIAL_PROFILES,
  defaultConnectionValues,
  EDITABLE_CREDENTIAL_FIELDS,
  maskCredentialValue,
  requiresSecretKey,
} from './domain/rules/credentialRules'

type BrokerAccountDoc = {
  id: number | string
  portfolio: number | string | { id: number | string }
  brokerType: 'alpaca' | 'interactive_brokers'
  environment: 'paper' | 'live'
}

function getRelationId(value: number | string | { id: number | string } | null | undefined): number | string | null {
  if (typeof value === 'object' && value !== null) return value.id
  return value ?? null
}

function encryptSecretField(
  data: Record<string, any>,
  plaintextField: string,
  encryptedField: string,
  ivField: string,
  authTagField: string,
  maskedField: string,
  encryptionSecret: string,
) {
  const plaintext = data[plaintextField]
  if (!plaintext) {
    delete data[plaintextField]
    return
  }

  const encrypted = encryptCredential(String(plaintext), encryptionSecret)

  data[encryptedField] = encrypted.ciphertext
  data[ivField] = encrypted.iv
  data[authTagField] = encrypted.authTag
  data[maskedField] = maskCredentialValue(String(plaintext))

  delete data[plaintextField]
}

/** Same as encryptSecretField, but the masked field shows a short SHA-256
 * fingerprint instead of the last 4 characters — for PEM keys, the last 4
 * characters are always the same boilerplate ("-----END..."), so they'd tell
 * you nothing about which key is on file. */
function encryptSecretFieldWithFingerprint(
  data: Record<string, any>,
  plaintextField: string,
  encryptedField: string,
  ivField: string,
  authTagField: string,
  maskedField: string,
  encryptionSecret: string,
) {
  const plaintext = data[plaintextField]
  if (!plaintext) {
    delete data[plaintextField]
    return
  }

  const encrypted = encryptCredential(String(plaintext), encryptionSecret)
  const fingerprint = crypto.createHash('sha256').update(String(plaintext)).digest('hex').slice(0, 8)

  data[encryptedField] = encrypted.ciphertext
  data[ivField] = encrypted.iv
  data[authTagField] = encrypted.authTag
  data[maskedField] = fingerprint

  delete data[plaintextField]
}

function resolveCredentialEncryptionSecret(): string {
  return (
    process.env.BROKER_CREDENTIAL_ENCRYPTION_KEY ||
    process.env.PAYLOAD_SECRET ||
    ''
  )
}

const encryptPlaintextValue = handleBeforeChangeHook({
  name: 'BrokerAccounts',
  operation: 'all',
  handler: async ({ data, originalDoc }) => {
    const portfolioId = getRelationId(
      (data.portfolio ?? (originalDoc as Record<string, unknown> | undefined)?.portfolio) as
        | number
        | string
        | { id: number | string }
        | null
        | undefined,
    )

    if (!portfolioId) {
      throw new Error('Portfolio is required for broker account.')
    }

    const effectiveBroker = String(data.brokerType ?? (originalDoc as Record<string, unknown> | undefined)?.brokerType ?? '')
    if (!effectiveBroker) {
      throw new Error('Broker type is required for broker account.')
    }

    if (data.brokerType === undefined) {
      data.brokerType = effectiveBroker
    }

    if (!(effectiveBroker in BROKER_CREDENTIAL_PROFILES)) {
      throw new Error('Unsupported broker type.')
    }

    const environment = String(data.environment ?? (originalDoc as Record<string, unknown> | undefined)?.environment ?? 'paper')
    const brokerType = effectiveBroker as 'alpaca' | 'interactive_brokers'
    const defaults = defaultConnectionValues(brokerType, environment as 'paper' | 'live')

    if (brokerType === 'alpaca' && !data.alpacaBaseUrl) {
      data.alpacaBaseUrl = defaults.alpacaBaseUrl
    }

    const encryptionSecret = resolveCredentialEncryptionSecret()
    if (!encryptionSecret) {
      throw new Error(
        'Missing encryption secret. Set BROKER_CREDENTIAL_ENCRYPTION_KEY or PAYLOAD_SECRET.',
      )
    }

    encryptSecretField(
      data,
      'apiKeyPlaintext',
      'apiKeyEncrypted',
      'apiKeyIv',
      'apiKeyAuthTag',
      'apiKeyMasked',
      encryptionSecret,
    )

    encryptSecretField(
      data,
      'secretKeyPlaintext',
      'secretKeyEncrypted',
      'secretKeyIv',
      'secretKeyAuthTag',
      'secretKeyMasked',
      encryptionSecret,
    )

    encryptSecretField(
      data,
      'ibConsumerKeyPlaintext',
      'ibConsumerKeyEncrypted',
      'ibConsumerKeyIv',
      'ibConsumerKeyAuthTag',
      'ibConsumerKeyMasked',
      encryptionSecret,
    )

    encryptSecretField(
      data,
      'ibAccessTokenPlaintext',
      'ibAccessTokenEncrypted',
      'ibAccessTokenIv',
      'ibAccessTokenAuthTag',
      'ibAccessTokenMasked',
      encryptionSecret,
    )

    encryptSecretField(
      data,
      'ibAccessTokenSecretPlaintext',
      'ibAccessTokenSecretEncrypted',
      'ibAccessTokenSecretIv',
      'ibAccessTokenSecretAuthTag',
      'ibAccessTokenSecretMasked',
      encryptionSecret,
    )

    encryptSecretFieldWithFingerprint(
      data,
      'ibSignatureKeyPemPlaintext',
      'ibSignatureKeyPemEncrypted',
      'ibSignatureKeyPemIv',
      'ibSignatureKeyPemAuthTag',
      'ibSignatureKeyPemMasked',
      encryptionSecret,
    )

    encryptSecretFieldWithFingerprint(
      data,
      'ibEncryptionKeyPemPlaintext',
      'ibEncryptionKeyPemEncrypted',
      'ibEncryptionKeyPemIv',
      'ibEncryptionKeyPemAuthTag',
      'ibEncryptionKeyPemMasked',
      encryptionSecret,
    )

    if (brokerType === 'alpaca') {
      const hasApiKey = Boolean(data.apiKeyEncrypted || (originalDoc as Record<string, unknown> | undefined)?.apiKeyEncrypted)
      const hasSecretKey = Boolean(data.secretKeyEncrypted || (originalDoc as Record<string, unknown> | undefined)?.secretKeyEncrypted)

      // Allow incremental credential entry in admin forms.
      // Incomplete credentials should not remain active.
      if ((!hasApiKey || (requiresSecretKey(brokerType) && !hasSecretKey)) && data.isActive === true) {
        data.isActive = false
      }
    }

    if (brokerType === 'interactive_brokers') {
      const original = originalDoc as Record<string, unknown> | undefined
      const hasIbAccountId = Boolean(data.ibAccountId || original?.ibAccountId)
      const hasConsumerKey = Boolean(data.ibConsumerKeyEncrypted || original?.ibConsumerKeyEncrypted)
      const hasAccessToken = Boolean(data.ibAccessTokenEncrypted || original?.ibAccessTokenEncrypted)
      const hasAccessTokenSecret = Boolean(data.ibAccessTokenSecretEncrypted || original?.ibAccessTokenSecretEncrypted)
      const hasSignatureKey = Boolean(data.ibSignatureKeyPemEncrypted || original?.ibSignatureKeyPemEncrypted)
      const hasEncryptionKey = Boolean(data.ibEncryptionKeyPemEncrypted || original?.ibEncryptionKeyPemEncrypted)
      const hasDhPrime = Boolean(data.ibDhPrime || original?.ibDhPrime)

      const complete =
        hasIbAccountId && hasConsumerKey && hasAccessToken && hasAccessTokenSecret &&
        hasSignatureKey && hasEncryptionKey && hasDhPrime

      if (!complete && data.isActive === true) {
        data.isActive = false
      }
    }

    delete data.apiKeyPlaintext
    delete data.secretKeyPlaintext

    return data
  },
})

export const brokerAccountsLifecycle = {
  beforeChange: [encryptPlaintextValue],
  afterChange: [syncVaultOnSave],
}
