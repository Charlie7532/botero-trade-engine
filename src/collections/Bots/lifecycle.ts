import { generateBotSlug } from './infrastructure/hooks/generateBotSlug'
import { syncAgentOnSave } from './infrastructure/hooks/syncAgentOnSave'
import { archiveAgentOnDelete } from './infrastructure/hooks/archiveAgentOnDelete'

export const botsLifecycle = {
  beforeChange: [generateBotSlug],
  afterChange: [syncAgentOnSave],
  afterDelete: [archiveAgentOnDelete],
}
