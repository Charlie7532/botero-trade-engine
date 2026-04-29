declare global {
  namespace NodeJS {
    interface ProcessEnv {
      CLAUDE_CODE_CACHE_CREATION_TOKENS?: string
      CLAUDE_CODE_CACHE_READ_TOKENS?: string
      CLAUDE_CODE_INPUT_TOKENS?: string
      CLAUDE_CODE_MODEL?: string
      CLAUDE_CODE_OUTPUT_TOKENS?: string
      CLAUDE_CODE_UPDATED_AT?: string
      PAYLOAD_SECRET: string
      DATABASE_URI: string
      NEXT_PUBLIC_SERVER_URL: string
      POSTGRES_URL?: string
      VERCEL_PROJECT_PRODUCTION_URL: string
    }
  }
}

// If this file has no import/export statements (i.e. is a script)
// convert it into a module by adding an empty export statement.
export {}
