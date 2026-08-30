import { NextRequest, NextResponse } from 'next/server'
import { getPayload } from 'payload'
import type { Where } from 'payload'
import configPromise from '@payload-config'

import { decryptValue } from '@/shared/domain/encryption'
import type { BrokerAccount } from '@/payload-types'

/**
 * POST /api/internal/broker-credentials
 *
 * Internal, service-to-service only. Called by the Python execution engine
 * to resolve which real broker account a portfolio should trade through,
 * and to get its credentials decrypted.
 *
 * This replaces the old pattern of the engine reading two hardcoded global
 * env vars (ALPACA_QUALITY_* / ALPACA_*) — those only covered exactly two
 * fixed accounts. Any portfolio/BrokerAccount created in the database can
 * now be resolved dynamically, without a code change or redeploy of the
 * engine.
 *
 * Auth: a dedicated bearer token (ENGINE_SERVICE_TOKEN), NOT a Payload user
 * API key. This intentionally does not reuse the "users API-Key" pattern
 * used elsewhere (e.g. PayloadInstrumentsAdapter) because that authenticates
 * AS a Payload user with that user's full collection access — broader blast
 * radius than we want for an endpoint whose whole job is to hand back
 * decrypted broker secrets. A single-purpose token, checked with a
 * constant-time comparison, keeps this endpoint's exposure to exactly what
 * it does.
 *
 * Request body (JSON):
 *   { "department": "quality" | "speculative", "brokerType": "alpaca" | "interactive_brokers" }
 *   — for the two legacy global accounts (no real per-person portfolios
 *   set up yet).
 *   Once real per-person portfolios exist, add portfolioId:
 *   { "portfolioId": string, "department": "quality" | "speculative", "brokerType": "..." }
 *
 *   department is ALWAYS required. A single portfolio can have MULTIPLE
 *   BrokerAccounts — one person, one real Alpaca login, but a separate
 *   BrokerAccount record per department (Portfolios.brokerAccounts is a
 *   one-to-many join) so quality vs. speculative capital is tracked
 *   separately. portfolioId alone would be ambiguous; portfolioId +
 *   department together identify exactly one account. If more than one
 *   active account still matches, this returns 500 (ambiguous_match)
 *   rather than silently picking one — trading through the wrong account
 *   because of a silent pick is worse than a loud failure.
 *
 * Response body (200):
 *   Alpaca:
 *     { "brokerType": "alpaca", "environment": "paper"|"live",
 *       "apiKey": string, "secretKey": string, "baseUrl": string,
 *       "accountRecordId": string }
 *   Interactive Brokers:
 *     { "brokerType": "interactive_brokers", "accountId": string,
 *       "consumerKey": string, "accessToken": string,
 *       "accessTokenSecret": string, "dhPrimeHex": string,
 *       "signatureKeyPem": string, "encryptionKeyPem": string,
 *       "accountRecordId": string }
 *
 * Never logs the decrypted values. Returns 404 (not "found but inactive",
 * just a flat 404) if no active, matching BrokerAccount exists, and 401 if
 * the service token doesn't match — same response either way to avoid
 * leaking which portfolios exist to a caller that doesn't even have the
 * token right.
 */

function timingSafeEqual(a: string, b: string): boolean {
  // Avoid throwing when lengths differ (Node's timingSafeEqual requires
  // equal-length buffers) while still not short-circuiting on length,
  // which is the actual timing side-channel we care about here.
  const bufA = Buffer.from(a)
  const bufB = Buffer.from(b)
  if (bufA.length !== bufB.length) {
    // Compare against a same-length dummy so the branch above doesn't
    // itself become a timing tell for "wrong length vs wrong content".
    const dummy = Buffer.alloc(bufA.length)
    require('crypto').timingSafeEqual(bufA, dummy)
    return false
  }
  return require('crypto').timingSafeEqual(bufA, bufB)
}

function isAuthorized(request: NextRequest): boolean {
  const expected = process.env.ENGINE_SERVICE_TOKEN
  if (!expected) return false // fail closed if the token isn't configured
  const header = request.headers.get('authorization') || ''
  const provided = header.startsWith('Bearer ') ? header.slice(7) : ''
  if (!provided) return false
  return timingSafeEqual(provided, expected)
}

interface BrokerCredentialsRequestBody {
  portfolioId?: string
  // Required whenever portfolioId is given: a single portfolio can have
  // MULTIPLE BrokerAccounts (Portfolios.brokerAccounts is a one-to-many
  // join — one person, one Alpaca login, but a separate BrokerAccount
  // record per department so quality/speculative capital is tracked
  // separately). portfolioId alone is ambiguous; portfolioId + department
  // together identify exactly one account.
  department?: 'quality' | 'speculative' | 'mixed'
  brokerType: 'alpaca' | 'interactive_brokers'
}

function resolveEncryptionSecret(): string {
  return process.env.BROKER_CREDENTIAL_ENCRYPTION_KEY || process.env.PAYLOAD_SECRET || ''
}

function decryptAlpacaCreds(account: BrokerAccount): { apiKey: string; secretKey: string } | null {
  const secret = resolveEncryptionSecret()
  if (!secret) return null
  if (
    !account.apiKeyEncrypted ||
    !account.apiKeyIv ||
    !account.apiKeyAuthTag ||
    !account.secretKeyEncrypted ||
    !account.secretKeyIv ||
    !account.secretKeyAuthTag
  ) {
    return null
  }
  try {
    const apiKey = decryptValue(
      { ciphertext: account.apiKeyEncrypted, iv: account.apiKeyIv, authTag: account.apiKeyAuthTag },
      secret,
    )
    const secretKey = decryptValue(
      { ciphertext: account.secretKeyEncrypted, iv: account.secretKeyIv, authTag: account.secretKeyAuthTag },
      secret,
    )
    return { apiKey, secretKey }
  } catch {
    return null
  }
}

function decryptGeneric(
  account: BrokerAccount,
  base: 'ibConsumerKey' | 'ibAccessToken' | 'ibAccessTokenSecret' | 'ibSignatureKeyPem' | 'ibEncryptionKeyPem',
  secret: string,
): string | null {
  const encrypted = account[`${base}Encrypted` as keyof BrokerAccount] as string | null | undefined
  const iv = account[`${base}Iv` as keyof BrokerAccount] as string | null | undefined
  const authTag = account[`${base}AuthTag` as keyof BrokerAccount] as string | null | undefined
  if (!encrypted || !iv || !authTag) return null
  try {
    return decryptValue({ ciphertext: encrypted, iv, authTag }, secret)
  } catch {
    return null
  }
}

function decryptIbCreds(account: BrokerAccount) {
  const secret = resolveEncryptionSecret()
  if (!secret) return null
  const consumerKey = decryptGeneric(account, 'ibConsumerKey', secret)
  const accessToken = decryptGeneric(account, 'ibAccessToken', secret)
  const accessTokenSecret = decryptGeneric(account, 'ibAccessTokenSecret', secret)
  const signatureKeyPem = decryptGeneric(account, 'ibSignatureKeyPem', secret)
  const encryptionKeyPem = decryptGeneric(account, 'ibEncryptionKeyPem', secret)
  if (!consumerKey || !accessToken || !accessTokenSecret || !signatureKeyPem || !encryptionKeyPem) {
    return null
  }
  return { consumerKey, accessToken, accessTokenSecret, signatureKeyPem, encryptionKeyPem }
}

export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    // Same shape/status whether the token is missing, wrong, or the account
    // doesn't exist — don't give a caller without the right token any signal.
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  let body: BrokerCredentialsRequestBody
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }

  const { portfolioId, department, brokerType } = body

  // department is ALWAYS required — it's what disambiguates which of a
  // portfolio's BrokerAccounts to use (a portfolio can have both a quality
  // and a speculative one). portfolioId is optional only for the legacy
  // two-global-account lookup that predates per-person portfolios.
  if (!brokerType || !department) {
    return NextResponse.json(
      { error: 'department_and_brokerType_required (portfolioId additionally required once real per-person portfolios exist)' },
      { status: 400 },
    )
  }

  const payload = await getPayload({ config: configPromise })

  const where: Where = {
    brokerType: { equals: brokerType },
    isActive: { equals: true },
    department: { equals: department },
  }
  if (portfolioId) {
    where.portfolio = { equals: portfolioId }
  }

  const result = await payload.find({
    collection: 'broker-accounts',
    where,
    limit: 2, // fetch 2, not 1 — lets us detect and reject an ambiguous match instead of silently picking one
    depth: 0,
  })

  if (result.docs.length > 1) {
    // Should be impossible given department disambiguates, but if it ever
    // happens (e.g. two active accounts mistakenly share portfolio+department),
    // silently picking one could mean trading through the wrong account.
    // Surface it loudly instead.
    return NextResponse.json(
      { error: 'ambiguous_match', detail: `${result.docs.length} active BrokerAccounts matched — expected exactly 1.` },
      { status: 500 },
    )
  }

  const account = result.docs[0] as BrokerAccount | undefined
  if (!account) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 })
  }

  if (brokerType === 'alpaca') {
    const creds = decryptAlpacaCreds(account)
    if (!creds) {
      // Credentials exist in the record shape but failed to decrypt — this
      // means either the encryption key rotated without re-encrypting
      // existing records, or the record was never actually saved with
      // credentials. Either way, do not fall back to anything — surface it.
      return NextResponse.json({ error: 'decryption_failed' }, { status: 500 })
    }
    const environment: 'paper' | 'live' = account.environment === 'live' ? 'live' : 'paper'
    const baseUrl =
      account.alpacaBaseUrl?.trim() ||
      (environment === 'live' ? 'https://api.alpaca.markets' : 'https://paper-api.alpaca.markets')

    return NextResponse.json({
      brokerType: 'alpaca',
      environment,
      apiKey: creds.apiKey,
      secretKey: creds.secretKey,
      baseUrl,
      accountRecordId: String(account.id),
    })
  }

  // Interactive Brokers — OAuth 1.0a Extended (First Party). See
  // ib_adapter.py's module docstring for what each of these fields is.
  const ibCreds = decryptIbCreds(account)
  if (!ibCreds) {
    return NextResponse.json({ error: 'decryption_failed_or_incomplete' }, { status: 500 })
  }
  if (!account.ibAccountId || !account.ibDhPrime) {
    return NextResponse.json({ error: 'incomplete_ib_account' }, { status: 500 })
  }

  return NextResponse.json({
    brokerType: 'interactive_brokers',
    accountId: account.ibAccountId,
    consumerKey: ibCreds.consumerKey,
    accessToken: ibCreds.accessToken,
    accessTokenSecret: ibCreds.accessTokenSecret,
    dhPrimeHex: account.ibDhPrime,
    signatureKeyPem: ibCreds.signatureKeyPem,
    encryptionKeyPem: ibCreds.encryptionKeyPem,
    accountRecordId: String(account.id),
  })
}
