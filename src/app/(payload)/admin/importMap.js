import { RscEntryLexicalCell as RscEntryLexicalCell_44fe37237e0ebf4470c9990d8cb7b07e } from '@payloadcms/richtext-lexical/rsc'
import { RscEntryLexicalField as RscEntryLexicalField_44fe37237e0ebf4470c9990d8cb7b07e } from '@payloadcms/richtext-lexical/rsc'
import { LexicalDiffComponent as LexicalDiffComponent_44fe37237e0ebf4470c9990d8cb7b07e } from '@payloadcms/richtext-lexical/rsc'
import { InlineToolbarFeatureClient as InlineToolbarFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { FixedToolbarFeatureClient as FixedToolbarFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { ParagraphFeatureClient as ParagraphFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { UnderlineFeatureClient as UnderlineFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { BoldFeatureClient as BoldFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { ItalicFeatureClient as ItalicFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { LinkFeatureClient as LinkFeatureClient_e70f5e05f09f93e00b997edb1ef0c864 } from '@payloadcms/richtext-lexical/client'
import { UserAvatarCell as UserAvatarCell_9fe0515a029c6b0db4b878b795bf4916 } from '@/collections/Users/components/UserAvatarCell'
import { PolicyRowLabel as PolicyRowLabel_5207e1226c827f6c9a0849ee6839f8ee } from '@/globals/SiteSettings/PolicyRowLabel'
import { default as default_2ca85bfe37efa5ce70ec84687778c385 } from '@/components/fields/ColorPicker'
import { RowLabel as RowLabel_b0b703649be0f5e367ab51fa1273eea2 } from '@/globals/SiteSettings/RowLabel'
import { default as default_f8aac8edd5dde803bbebb1dadcc3c472 } from '@/components/Admin/PayloadAdminAvatar'
import { default as default_b071f7683a0bf61183f98194697e6e39 } from '@/components/Admin/EmptyLogoutButton'
import { default as default_94a6a70cbadb7fb6025ad84852bbcc14 } from '@/components/Logo/AppLogoCompact '
import { default as default_b8eccbc6e976e9f5be666a1b4a18a98c } from '@/components/Logo/AppLogoExpanded'
import { default as default_57542a803be6bc6602169e617924d624 } from '@/components/SidebarHomeButton'
import { default as default_fe6522ffb7de26dad8c594d3f8d9234a } from '@/components/Admin/AdminHeroUIProvider'
import { VercelBlobClientUploadHandler as VercelBlobClientUploadHandler_16c82c5e25f430251a3e3ba57219ff4e } from '@payloadcms/storage-vercel-blob/client'
import { default as default_06f0c125fb9975bb64801182c7efa4bd } from '@/widgets/ClaudeTokenConsumption'
import { default as default_994ac1d3cc16da241546b3d54cb8f882 } from '@/widgets/ClaudeTokenBreakdown'
import { default as default_bcb9ddc6b82a8907d040da4d3cb24e11 } from '@/widgets/NeonCpu'
import { default as default_3fe3dbeb42bbf71713dfaecac3ee7f2a } from '@/widgets/NeonCache'
import { default as default_236006c85f42b5e49e29bf0bd6f0cf3f } from '@/widgets/PostgresConnections'
import { default as default_e95235a385e987c84081adf2e839f5c1 } from '@/widgets/PoolerConnections'
import { CollectionCards as CollectionCards_f9c02e79a4aed9a3924487c0cd4cafb1 } from '@payloadcms/next/rsc'

/** @type import('payload').ImportMap */
export const importMap = {
  "@payloadcms/richtext-lexical/rsc#RscEntryLexicalCell": RscEntryLexicalCell_44fe37237e0ebf4470c9990d8cb7b07e,
  "@payloadcms/richtext-lexical/rsc#RscEntryLexicalField": RscEntryLexicalField_44fe37237e0ebf4470c9990d8cb7b07e,
  "@payloadcms/richtext-lexical/rsc#LexicalDiffComponent": LexicalDiffComponent_44fe37237e0ebf4470c9990d8cb7b07e,
  "@payloadcms/richtext-lexical/client#InlineToolbarFeatureClient": InlineToolbarFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#FixedToolbarFeatureClient": FixedToolbarFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#ParagraphFeatureClient": ParagraphFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#UnderlineFeatureClient": UnderlineFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#BoldFeatureClient": BoldFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#ItalicFeatureClient": ItalicFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@payloadcms/richtext-lexical/client#LinkFeatureClient": LinkFeatureClient_e70f5e05f09f93e00b997edb1ef0c864,
  "@/collections/Users/components/UserAvatarCell#UserAvatarCell": UserAvatarCell_9fe0515a029c6b0db4b878b795bf4916,
  "@/globals/SiteSettings/PolicyRowLabel#PolicyRowLabel": PolicyRowLabel_5207e1226c827f6c9a0849ee6839f8ee,
  "@/components/fields/ColorPicker#default": default_2ca85bfe37efa5ce70ec84687778c385,
  "@/globals/SiteSettings/RowLabel#RowLabel": RowLabel_b0b703649be0f5e367ab51fa1273eea2,
  "@/components/Admin/PayloadAdminAvatar#default": default_f8aac8edd5dde803bbebb1dadcc3c472,
  "@/components/Admin/EmptyLogoutButton#default": default_b071f7683a0bf61183f98194697e6e39,
  "@/components/Logo/AppLogoCompact #default": default_94a6a70cbadb7fb6025ad84852bbcc14,
  "@/components/Logo/AppLogoExpanded#default": default_b8eccbc6e976e9f5be666a1b4a18a98c,
  "@/components/SidebarHomeButton#default": default_57542a803be6bc6602169e617924d624,
  "@/components/Admin/AdminHeroUIProvider#default": default_fe6522ffb7de26dad8c594d3f8d9234a,
  "@payloadcms/storage-vercel-blob/client#VercelBlobClientUploadHandler": VercelBlobClientUploadHandler_16c82c5e25f430251a3e3ba57219ff4e,
  "@/widgets/ClaudeTokenConsumption#default": default_06f0c125fb9975bb64801182c7efa4bd,
  "@/widgets/ClaudeTokenBreakdown#default": default_994ac1d3cc16da241546b3d54cb8f882,
  "@/widgets/NeonCpu#default": default_bcb9ddc6b82a8907d040da4d3cb24e11,
  "@/widgets/NeonCache#default": default_3fe3dbeb42bbf71713dfaecac3ee7f2a,
  "@/widgets/PostgresConnections#default": default_236006c85f42b5e49e29bf0bd6f0cf3f,
  "@/widgets/PoolerConnections#default": default_e95235a385e987c84081adf2e839f5c1,
  "@payloadcms/next/rsc#CollectionCards": CollectionCards_f9c02e79a4aed9a3924487c0cd4cafb1
}
