import { payloadCloudPlugin } from '@payloadcms/payload-cloud'
import { formBuilderPlugin } from '@payloadcms/plugin-form-builder'
import { seoPlugin } from '@payloadcms/plugin-seo'
import { Plugin } from 'payload'
import { GenerateTitle, GenerateURL } from '@payloadcms/plugin-seo/types'
import { FixedToolbarFeature, HeadingFeature, lexicalEditor } from '@payloadcms/richtext-lexical'

import { getServerSideURL } from '@/utilities/getURL'
import { OAuth2Plugin } from 'payload-oauth2'

type SeoDoc = {
  title?: string | null
  slug?: string | null
}

const generateTitle: GenerateTitle<SeoDoc> = ({ doc }) => {
  return doc?.title ? `${doc.title} | Main 12 web Template` : 'Main 12 web Template'
}

const generateURL: GenerateURL<SeoDoc> = ({ doc }) => {
  const url = getServerSideURL()

  return doc?.slug ? `${url}/${doc.slug}` : url
}

export const plugins: Plugin[] = [
  seoPlugin({
    generateTitle,
    generateURL,
  }),
  formBuilderPlugin({
    fields: {
      payment: false,
    },
    formOverrides: {
      admin: {
        group: 'Website',
      },
      fields: ({ defaultFields }) => {
        return defaultFields.map((field) => {
          if ('name' in field && field.name === 'confirmationMessage') {
            return {
              ...field,
              editor: lexicalEditor({
                features: ({ rootFeatures }) => {
                  return [
                    ...rootFeatures,
                    FixedToolbarFeature(),
                    HeadingFeature({ enabledHeadingSizes: ['h1', 'h2', 'h3', 'h4'] }),
                  ]
                },
              }),
            }
          }
          return field
        })
      },
    },
    formSubmissionOverrides: {
      admin: {
        group: 'Website',
      },
    },
  }),
  OAuth2Plugin({
    enabled: true,
    strategyName: "google",
    useEmailAsIdentity: true,
    serverURL: process.env.NEXT_PUBLIC_SERVER_URL || "http://localhost:3000",
    clientId: process.env.GOOGLE_CLIENT_ID || "",
    clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
    tokenEndpoint: "https://oauth2.googleapis.com/token",
    providerAuthorizationUrl: "https://accounts.google.com/o/oauth2/v2/auth",
    scopes: [
      "openid",
      "https://www.googleapis.com/auth/userinfo.email",
      "https://www.googleapis.com/auth/userinfo.profile",
    ],
    authorizePath: "/oauth/google",
    callbackPath: "/oauth/google/callback",
    getUserInfo: async (accessToken: string) => {
      const response = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const user = await response.json();
      return {
        email: user.email,
        sub: user.sub,
        name: user.name,
      };
    },
    successRedirect: (req) => req.searchParams.get('state') || '/account',
    failureRedirect: (req) => {
      const fallback = req.searchParams.get('state') || '/login'
      const separator = fallback.includes('?') ? '&' : '?'
      return `${fallback}${separator}error=Google+login+failed`
    },
  }),
  payloadCloudPlugin(),
]
