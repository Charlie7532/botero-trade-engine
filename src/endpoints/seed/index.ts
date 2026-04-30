import type { Payload, PayloadRequest } from 'payload'

// Blog/demo seed is not applicable to this trading project (no Pages/Posts collections).
export const seed = async ({
  payload,
}: {
  payload: Payload
  req: PayloadRequest
}): Promise<void> => {
  payload.logger.info('Seed not configured for this project.')
}
