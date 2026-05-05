import { autoGenerateSlugAndOwner } from './interface/hooks/autoGenerateSlugAndOwner'
import { createOwnerMembershipHook } from './interface/hooks/createOwnerMembership'

export const portfoliosLifecycle = {
  beforeChange: [autoGenerateSlugAndOwner],
  afterChange: [createOwnerMembershipHook],
}

