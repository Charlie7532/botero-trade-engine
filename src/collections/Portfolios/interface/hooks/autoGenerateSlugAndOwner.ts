import { handleBeforeChangeHook } from '@/shared/handlers'
import { generatePortfolioSlug, isValidPortfolioSlug } from '../../domain/rules/accountRules'

export const autoGenerateSlugAndOwner = handleBeforeChangeHook({
  name: 'Portfolios',
  operation: ['create', 'update'],
  handler: async ({ data, req, operation }) => {
    if (operation === 'create') {
      if (!data.slug) {
        data.slug = generatePortfolioSlug()
      } else if (!isValidPortfolioSlug(String(data.slug))) {
        throw new Error('Portfolio slug must be a valid 12-character alphanumeric value.')
      }
    }

    if (req.user && !data.owner) {
      data.owner = req.user.id
    }

    return data
  },
})
