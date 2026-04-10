import type {
  CollectionBeforeChangeHook,
  CollectionAfterChangeHook,
  CollectionAfterDeleteHook,
  CollectionBeforeValidateHook,
  CollectionBeforeDeleteHook,
  CollectionBeforeOperationHook,
  CollectionAfterReadHook,
  GlobalAfterChangeHook,
} from 'payload'

type OperationName = 'create' | 'update' | 'delete' | 'read' | 'all'

interface HookConfig<HookType extends (...args: any[]) => any> {
  name: string
  operation?: OperationName | OperationName[]
  guards?: Array<(args: Parameters<HookType>[0]) => boolean | Promise<boolean>>
  handler: HookType
}

export function handleBeforeChangeHook(
  config: HookConfig<CollectionBeforeChangeHook>
): CollectionBeforeChangeHook {
  return async (args) => {
    if (config.operation && config.operation !== 'all') {
      const ops = Array.isArray(config.operation) ? config.operation : [config.operation]
      if (!ops.includes(args.operation as OperationName)) {
        return args.data
      }
    }

    if (config.guards) {
      for (const guard of config.guards) {
        const pass = await guard(args)
        if (!pass) return args.data
      }
    }

    try {
      return await config.handler(args)
    } catch (error) {
      console.error(`[${config.name}] Error in beforeChange hook:`, error)
      throw error
    }
  }
}

export function handleAfterChangeHook(
  config: HookConfig<CollectionAfterChangeHook>
): CollectionAfterChangeHook {
  return async (args) => {
    if (config.operation && config.operation !== 'all') {
      const ops = Array.isArray(config.operation) ? config.operation : [config.operation]
      if (!ops.includes(args.operation as OperationName)) {
        return args.doc
      }
    }

    if (config.guards) {
      for (const guard of config.guards) {
        const pass = await guard(args)
        if (!pass) return args.doc
      }
    }

    try {
      return await config.handler(args)
    } catch (error) {
      console.error(`[${config.name}] Error in afterChange hook:`, error)
      return args.doc
    }
  }
}

export function handleAfterDeleteHook(
  config: HookConfig<CollectionAfterDeleteHook>
): CollectionAfterDeleteHook {
  return async (args) => {
    if (config.guards) {
      for (const guard of config.guards) {
        const pass = await guard(args)
        if (!pass) return args.doc
      }
    }

    try {
      return await config.handler(args)
    } catch (error) {
      console.error(`[${config.name}] Error in afterDelete hook:`, error)
      return args.doc
    }
  }
}

export function handleAfterReadHook(
  config: HookConfig<CollectionAfterReadHook>
): CollectionAfterReadHook {
  return async (args) => {
    if (config.guards) {
      for (const guard of config.guards) {
        const pass = await guard(args)
        if (!pass) return args.doc
      }
    }

    try {
      return await config.handler(args)
    } catch (error) {
      console.error(`[${config.name}] Error in afterRead hook:`, error)
      return args.doc
    }
  }
}

export function handleGlobalAfterChangeHook(
  config: HookConfig<GlobalAfterChangeHook>
): GlobalAfterChangeHook {
  return async (args) => {
    if (config.guards) {
      for (const guard of config.guards) {
        const pass = await guard(args)
        if (!pass) return args.doc
      }
    }

    try {
      return await config.handler(args)
    } catch (error) {
      console.error(`[${config.name}] Error in global afterChange hook:`, error)
      return args.doc
    }
  }
}

