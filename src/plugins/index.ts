import { payloadCloudPlugin } from '@payloadcms/payload-cloud'
import { Plugin } from 'payload'

import { OAuth2Plugin } from 'payload-oauth2'
import { vercelBlobStorage } from '@payloadcms/storage-vercel-blob'
import { mcpPlugin } from '@payloadcms/plugin-mcp'

export const plugins: Plugin[] = [
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
    successRedirect: (req) => req.searchParams.get('state') || '/portafolio',
    failureRedirect: (req) => {
      const fallback = req.searchParams.get('state') || '/login'
      const separator = fallback.includes('?') ? '&' : '?'
      return `${fallback}${separator}error=Google+login+failed`
    },
  }),
  payloadCloudPlugin(),
  mcpPlugin({
    collections: {
      AgentSkills: { enabled: true },
      Portfolios: { enabled: true },
      Bots: { enabled: true },
      McpServers: { enabled: true },
    },
  }),
  vercelBlobStorage({
    collections: {
      media: {
        prefix: process.env.PROJECT_ID ? `${process.env.PROJECT_ID}/media` : 'media',
      },
      'user-avatar': {
        prefix: process.env.PROJECT_ID ? `${process.env.PROJECT_ID}/avatars` : 'avatars',
      },
    },
    token: process.env.BLOB_READ_WRITE_TOKEN,
  }),
]
