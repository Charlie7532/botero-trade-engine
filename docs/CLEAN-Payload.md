# Resumen Ejecutivo

**Fecha:** 2026-03-19

**Proyecto:** PaintPulse App

**Stack:** Next.js 15 + Payload CMS 3 + PostgreSQL + React 19

PaintPulse utiliza Payload CMS como ORM y CMS headless. Payload impone un modelo donde definicion de esquema, logica de negocio, control de acceso y configuracion admin coexisten en un mismo archivo de collection. Esto genera dos problemas principales:

1. **Discovery Problem**: No existe un lugar donde ver "cuando X ocurre, estas cosas pasan en este orden". Para entender el flujo de una operacion hay que rastrear imports entre multiples archivos.
2. **Divergencia Admin/API**: La logica de negocio vive en API routes custom (`src/app/api/v2/`), lo que significa que el panel admin de Payload no ejecuta los mismos flujos.

Este informe propone **10 patrones** para aplicar Clean Architecture de forma incremental, sin reescribir el sistema.

---

# 1. Diagnostico del Estado Actual

## 1.1 Collections = God Objects

Cada collection en `src/collections/*/index.ts` mezcla:

- **Esquema** (fields, labels, UI config)
- **Logica de negocio** (hooks: beforeChange, afterChange, afterDelete)
- **Control de acceso** (access rules)
- **Configuracion admin** (custom components, groups)

Ejemplo: `Campaigns/index.ts` tiene hooks que auto-asignan account, validan suscripcion, crean recipients, activan campanas y emiten eventos — todo en un solo objeto.

## 1.2 Hooks = Logica Invisible

Los hooks de Payload son equivalentes a triggers de base de datos — se ejecutan implicitamente cuando Payload hace operaciones CRUD:

- **No se sabe cuando se ejecutan** sin leer la collection
- **Efectos secundarios ocultos**: `updateLeadStatus` modifica Leads cuando se actualiza un Project
- **Orden de ejecucion opaco**: multiples afterChange hooks en array

## 1.3 Service Layer = Solo HTTP Client

Los services en `src/services/` son wrappers de `fetcher()` — no contienen logica de negocio. La logica real vive en hooks y route handlers.

## 1.4 Dos Caminos = Dos Comportamientos

```
Camino A (API):   POST /api/v2/renders → route handler → logica de ~1000 lineas
Camino B (Admin): Admin panel → payload.create() → hooks (sin la logica del endpoint)
```

Si la logica vive en el route handler, el admin no la ejecuta. Resultado: bugs silenciosos.

## 1.5 Manejo de Errores Inconsistente

| Capa | Patron actual |
| --- | --- |
| API routes | `ControlException` hierarchy (400-500) |
| Use cases | Mix de throw y catch silencioso |
| Hooks (beforeChange) | `throw new Error()` |
| Hooks (afterChange) | `handleAfterChangeHook` catch + log |
| Payments/access | `SubscriptionAccessResult` (Result pattern) |
| Server actions | `ActionResult<T>` (discriminated union) |

## 1.6 Lo que Ya Funciona Bien

- `handleAfterChangeHook()` con guards y names
- `src/payments/access/` — logica de suscripcion extraida
- `src/lib/events/` — eventos desacoplados
- Service layer (interfaz + clase + singleton)
- Jobs system con retry y exponential backoff
- Error wrappers centralizados

---

# 2. Arquitectura Propuesta

## 2.1 Capas

```
+---------------------------------------------------+
|  Payload Hooks / API Routes / Job Handlers        |  ← Framework layer
|  Thin adapters: deserializar, instanciar,         |
|  llamar use case, devolver resultado              |
+---------------------------------------------------+
|  Use Cases (orquestacion)                         |  ← Application layer
|  Reciben ports inyectados, coordinan reglas       |
|  y side-effects. No importan Payload.             |
+---------------------------------------------------+
|  Domain Rules (funciones puras)                   |  ← Domain layer
|  Predicados, transformaciones, validaciones.      |
|  0 dependencias externas, 0 I/O.                  |
+---------------------------------------------------+
|  Ports (interfaces)                               |  ← Contratos
|  LeadRepository, JobQueue, EventEmitter, etc.     |
+---------------------------------------------------+
```

## 2.2 Regla de Dependencia

```jsx
modules/*/domain/rules/*.ts            → 0 imports externos
modules/*/domain/useCases/*.ts         → solo importa de domain/ (rules + ports)
modules/*/infrastructure/payload/*.ts  → importa de domain/ports/ + payload
modules/*/interface/hooks/*.ts         → importa de infrastructure/ + domain/useCases/
```

Nunca al reves. El dominio nunca conoce a Payload.

## 2.3 Estructura de Carpetas (Recomendada por Modulo)

```jsx
src/
├── modules/
│   ├── projects/
│   │   ├── domain/                    # reglas, use cases, ports, modelos, errores
│   │   │   ├── rules/
│   │   │   ├── useCases/
│   │   │   ├── ports/
│   │   │   ├── models/
│   │   │   └── errors.ts
│   │   ├── infrastructure/
│   │   │   └── payload/
│   │   │       ├── repositories/
│   │   │       └── mappers/
│   │   ├── interface/
│   │   │   ├── hooks/
│   │   │   ├── lifecycle.ts
│   │   │   ├── api/
│   │   │   └── jobs/
│   │   └── index.ts
│   ├── campaigns/
│   └── leads/
├── shared/
│   ├── kernel/                        # Result, errores base, tipos comunes
│   ├── handlers/                      # wrappers handle*Hook, handlerRoute
│   └── utils/
├── platform/
│   ├── payload/                       # payload.config, plugins, config global
│   ├── queue/                         # worker runtime
│   └── next/                          # middleware y bootstrap
├── collections/                       # coexistencia durante migracion incremental
├── services/                          # HTTP clients (sin cambios)
├── jobs/                              # thin adapters (coexistencia)
└── app/                               # Next.js routes
```

## 2.4 Decision de Nomenclatura: `server` -> `infrastructure`

- `server` describe entorno de ejecucion.
- `infrastructure` describe responsabilidad arquitectonica.
- Evita confusion con Server Components / Server Actions en Next.js.

## 2.5 Politica de Dependencias

- `domain` no importa de `infrastructure`, `interface`, `platform`, `app`, `payload` ni `next`.
- `infrastructure` implementa ports e importa `domain`.
- `interface` (hooks/routes/jobs) importa `domain` + `infrastructure`.
- `shared` no depende de modulos de negocio.
- No se permiten imports cruzados directos entre modulos sin contrato explicito.

---

# 3. Los 10 Patrones

## 3.1 Lifecycle Manifest

**Resuelve:** Discovery Problem

Un solo archivo por collection que documenta y exporta todo el ciclo de vida:

```tsx
// src/collections/Projects/lifecycle.ts
import {
  handleAfterChangeHook,
  handleBeforeChangeHook,
  handleAfterDeleteHook,
} from "@/shared/handlers";

/**
 * PROJECT LIFECYCLE
 * beforeChange:
 *   - validateSubscription: blocks create if over limit
 * afterChange:
 *   - onCreate: emitProjectCreated
 *   - onUpdate: emitProjectUpdated
 *   - onLink(lead): qualifyLead -> updates Lead.status
 * afterDelete:
 *   - emitProjectDeleted
 */

const validateSubscriptionHook = handleBeforeChangeHook<Project>({
  name: "Projects",
  operation: "create",
  guards: [({ req }) => !req.context?.skipHooks],
  handler: async ({ data, req }) => {
    await validateSubscriptionBeforeChange("project")({ data, req } as any);
    return data;
  },
});

const updateLeadStatusHook = handleAfterChangeHook<Project>({
  name: "Projects",
  operation: "update",
  guards: [
    ({ req }) => !req.context?.skipHooks,
    ({ doc }) => !!doc.lead,
  ],
  handler: async ({ doc, req, previousDoc }) => {
    await updateLeadStatus({ doc, req, previousDoc } as any);
    return doc;
  },
});

const emitProjectCreatedEventHook = handleAfterChangeHook<Project>({
  name: "Projects",
  operation: "create",
  guards: [({ req }) => !req.context?.skipHooks],
  handler: async ({ doc, req, previousDoc }) => {
    await emitProjectCreatedEvent({ doc, req, previousDoc } as any);
    return doc;
  },
});

const emitProjectUpdatedEventHook = handleAfterChangeHook<Project>({
  name: "Projects",
  operation: "update",
  guards: [
    ({ req }) => !req.context?.skipHooks,
    ({ doc, previousDoc }) => doc.status !== previousDoc.status,
  ],
  handler: async ({ doc, req, previousDoc }) => {
    await emitProjectUpdatedEvent({ doc, req, previousDoc } as any);
    return doc;
  },
});

const emitProjectDeletedEventHook = handleAfterDeleteHook<Project>({
  name: "Projects",
  guards: [({ req }) => !req.context?.skipHooks],
  handler: async ({ doc, req }) => {
    await emitProjectDeletedEvent({ doc, req } as any);
  },
});

export const projectLifecycle = {
  beforeChange: [validateSubscriptionHook],
  afterChange: [updateLeadStatusHook, emitProjectCreatedEventHook, emitProjectUpdatedEventHook],
  afterDelete: [emitProjectDeletedEventHook],
};
```

El `index.ts` queda con `hooks: projectLifecycle` — una sola linea.

## 3.2 Use Cases Independientes

**Resuelve:** Logica acoplada a Payload

**Regla de oro:** Si un hook tiene un `if`, esa condicion es logica de negocio — debe vivir fuera del hook.

```tsx
// domain/leads/rules.ts — PURO
export function shouldQualifyLead(status: string): boolean {
  return status === 'new' || status === 'contacted';
}

// domain/leads/qualifyLeadOnProjectLink.ts — USE CASE
export async function qualifyLeadOnProjectLink(
  leadRepo: LeadRepository, leadId: string
): Promise<void> {
  const lead = await leadRepo.findById(leadId);
  if (!shouldQualifyLead(lead.status)) return;
  await leadRepo.update(leadId, buildQualifiedLeadData());
}

// collections/Projects/hooks/updateLeadStatus.ts — THIN ADAPTER
export const updateLeadStatus: CollectionAfterChangeHook = async ({ doc, req }) => {
  const leadRepo = new PayloadLeadRepository(req.payload);
  await qualifyLeadOnProjectLink(leadRepo, leadId);
  return doc;
};
```

**Test sin Payload:**

```tsx
const mockRepo = { findById: vi.fn(), update: vi.fn() };
mockRepo.findById.mockResolvedValue({ id: '1', status: 'new' });
await qualifyLeadOnProjectLink(mockRepo, '1');
expect(mockRepo.update).toHaveBeenCalled();
```

## 3.3 Ports and Adapters

**Resuelve:** Inversion de dependencias

| Port (interfaz) | Responsabilidad | Adapter |
| --- | --- | --- |
| `LeadRepository` | CRUD de Leads | `PayloadLeadRepository` |
| `ProjectRepository` | CRUD de Projects | `PayloadProjectRepository` |
| `CampaignRepository` | CRUD + Recipients | `PayloadCampaignRepository` |
| `JobQueue` | Encolar trabajos async | `PayloadJobQueue` |
| `EventEmitter` | Emitir eventos | `PayloadEventEmitter` |
| `MailService` | Correo directo | `StannpMailService` |
| `SubscriptionChecker` | Validar acceso | `PayloadSubscriptionChecker` |

## 3.4 Validacion: Zod en Boundaries, Reglas en Domain

**Resuelve:** Donde validar datos

| Tipo | Donde | Herramienta |
| --- | --- | --- |
| Forma del input | API route / hook (boundary) | Zod |
| Reglas de negocio | `domain/*/rules.ts` | Funciones puras |
| Integridad de datos | Payload / DB | Constraints |

El use case recibe datos ya validados. Zod opera en la frontera, nunca dentro del use case.

```tsx
// Boundary (Zod) — "tienen la forma correcta?"
const schema = z.object({ radiusMiles: z.number().positive() });

// Domain (regla) — "es aceptable para el negocio?"
export function isValidRadius(miles: number): boolean {
  return miles >= 1 && miles <= 50;
}
```

## 3.5 API Routes como Boundaries

**Resuelve:** Routes de 1000+ lineas

El route solo debe: parsear request, validar con Zod, instanciar adapters, llamar use case, serializar respuesta.

```tsx
// ANTES: renders/route.ts (~1000 lineas, toda la logica)
// DESPUES: renders/route.ts (~30 lineas)
export const POST = handlerRoute(async (request) => {
  const input = createRenderSchema.parse(body);
  const render = await createRender(mediaRepo, renderRepo, webhookService, input);
  return NextResponse.json({ success: true, data: render });
});
```

## 3.6 Hooks como Punto Unico de Entrada (Admin = API)

**Resuelve:** El problema fundamental — Admin y API ejecutan la misma logica

```
                  ┌─────────────┐
API Route ──────→ │             │
                  │  payload.*  │ ──→ Hooks ──→ Use Cases
Admin Panel ────→ │  (Local API)│
                  │             │
Job Handler ────→ │             │
                  └─────────────┘
```

Todo pasa por Payload Local API. Los hooks son el unico lugar donde la logica se ejecuta siempre.

| Accion | API | Admin | Job |
| --- | --- | --- | --- |
| Crear render | `payload.create()` → hooks | Save → `payload.create()` → hooks | Job → `payload.create()` → hooks |
| Activar campaign | `payload.update()` → hooks | Cambiar status → Save → hooks | N/A |

**Cuando SI se necesita endpoint custom:**

1. Composicion pre-Payload (download image, resize)
2. Multi-collection atomics
3. Integracion externa pura (proxy a Stannp)
4. Queries complejas

## 3.7 Manejo de Errores entre Capas

**Resuelve:** Inconsistencia en tipos de error

```tsx
// src/domain/errors.ts
export class DomainError extends Error {
  constructor(message: string, public readonly code: string) {
    super(message);
  }
}
export class InvalidTransitionError extends DomainError { ... }
export class ResourceLimitError extends DomainError { ... }
export class NotFoundError extends DomainError { ... }
```

**Traduccion en handlerRoute:**

```tsx
const DOMAIN_ERROR_STATUS = {
  VALIDATION_ERROR: 400,
  INVALID_TRANSITION: 409,
  RESOURCE_LIMIT: 403,
  NOT_FOUND: 404,
};
```

| Capa | Lanza | Atrapa |
| --- | --- | --- |
| `domain/rules` | No lanza (boolean) | Nada |
| `domain/useCases` | `DomainError` | Nada (propaga) |
| `adapters/payload` | Wrap Payload errors | Errores de Payload |
| hooks (before) | Propaga DomainError | Nada |
| hooks (after) | handleAfterChangeHook catchea | Todo |
| API routes | handlerRoute catchea | DomainError → HTTP |

## 3.8 Jobs como Use Cases Async

**Resuelve:** Logica de jobs acoplada a Payload

Job handlers se vuelven thin adapters:

```tsx
// jobs/handlers/campaignActivate.ts — ADAPTER
export async function handleCampaignActivate(context, jobPayload) {
  const campaignRepo = new PayloadCampaignRepository(payload);
  const jobQueue = new PayloadJobQueue(payload);
  await onActivateCampaign(campaignRepo, jobQueue, {
    campaignId: jobPayload.campaignId,
  });
}
```

**Errores en jobs:**

- DomainError permanente → dead letter, no retry
- Error transitorio (API timeout) → retry automatico

## 3.9 Webhooks/Eventos como Side-Effects

**Resuelve:** Eventos dispersos en hooks

Eventos se emiten a traves de un port `EventEmitter`:

```tsx
// domain/renders/triggerRenderProcessing.ts
export async function triggerRenderProcessing(
  jobQueue: JobQueue, eventEmitter: EventEmitter, renderId: string
) {
  await jobQueue.enqueue('render.process', { renderId });
  await eventEmitter.emit('render.created', { renderId });
}
```

Eventos explicitos en el use case, testeables con mock.

## 3.10 Wrappers de Hooks como Estandar de Legibilidad

**Resuelve:** Opacidad del flujo, inconsistencia de errores y baja trazabilidad.

Todos los hooks de collections deben declararse usando wrappers de `@/shared/handlers` (o `@/infrastructure/handlers` si se decide mantenerlos ahi durante la transicion).

Esto hace explicita y homogenea la estructura de cada hook: `name`, `operation`, `guards`, `handler`.

**Wrappers estandar por tipo de hook**

- `handleBeforeValidateHook`
- `handleBeforeChangeHook`
- `handleAfterChangeHook`
- `handleBeforeDeleteHook`
- `handleAfterDeleteHook`
- `handleBeforeOperationHook`
- `handleAfterOperationHook`

**Regla**

- No se exportan hooks raw (sin wrapper), salvo excepcion documentada en el `lifecycle.ts` de la collection.

**Beneficios directos**

- Logging estructurado consistente por collection/operacion.
- Filtro por operacion sin `if` repetidos.
- Guards declarativos para precondiciones.
- Fallback seguro y manejo uniforme de errores segun tipo de hook.

```tsx
export const validateSubscriptionHook = handleBeforeChangeHook<Project>({
  name: "Projects",
  operation: "create",
  guards: [({ req }) => !req.context?.skipHooks],
  handler: async ({ data, req }) => {
    await assertActiveSubscription(req);
    return data;
  },
});
```

Impacto en discovery:

- Cada hook tiene una forma estandar y un nombre explicito.
- El `lifecycle.ts` se convierte en un manifiesto legible del comportamiento real.

---

# 4. Flujo End-to-End: Campaign Activate

```
1. Usuario (Admin o API) cambia status a "active"
   ├─ API: PATCH .../campaigns/:id → payload.update()
   └─ Admin: Save → payload.update()

2. beforeChange hooks
   └─ validateSubscription → checkAccess use case

3. Payload persiste el documento

4. afterChange hooks (lifecycle.ts)
   └─ onActivate (guard: isActivationTransition)
      └─ activateCampaign use case
         ├─ Valida transicion (domain rule)
         ├─ jobQueue.enqueue('campaign.activate')
         └─ eventEmitter.emit('campaign.activated')

5. Cron → runWorker() → campaign.activate
   └─ onActivateCampaign use case
      ├─ Fetch recipients
      └─ Encolar render jobs por recipient

6. Cron → queue.createRender (concurrent, batch 5)
   └─ createRenderForQueue use case

7. Webhook delivery (async)
   └─ HMAC signed POST
```

**Un solo flujo. Admin o API. Mismos use cases. Mismos eventos.**

---

# 5. Reglas Practicas

## Cuando extraer a domain/

| Senal en el hook | Accion |
| --- | --- |
| Tiene un `if` con logica de decision | Extraer a `domain/*/rules.ts` |
| Coordina multiples collections | Crear use case en `domain/*/` |
| Llama a `req.payload` directamente | Crear port + adapter |
| Tiene constantes (estados, limites) | Mover a `domain/*/rules.ts` |
| Es transformacion de datos | Funcion pura en `domain/*/rules.ts` |

## Que hace cada capa

| Capa | Responsabilidad | Importa de |
| --- | --- | --- |
| `domain/rules` | Predicados, validaciones | Nada externo |
| `domain/useCases` | Orquestar reglas + ports | domain/rules, domain/ports |
| `domain/ports` | Interfaces | payload-types (solo tipos) |
| `modules/*/infrastructure/payload` | Implementar ports | domain/ports, payload |
| `modules/*/interface/hooks` | Thin adapter con wrappers `handle*Hook` | infrastructure/, domain/useCases, @/shared/handlers |
| `modules/*/interface/lifecycle.ts` | Manifest + composicion | modules/*/interface/hooks |
| `shared/handlers` | Error boundaries y wrappers cross-cutting | shared/kernel, domain/errors |
| `modules/*/interface/api/schemas` | Contratos de API (Zod) por modulo | Nada de domain |
| `modules/*/interface/jobs` | Thin adapter para jobs | infrastructure/, domain/useCases |
| `modules/*/interface/api` | HTTP boundary | schemas, infrastructure, domain |

---

# 6. Estrategia de Adopcion Incremental

**No se requiere big-bang.** Aplicar patron por patron, collection por collection.

## Fase 0 — Lifecycle Manifests + Normalizacion de Wrappers

- Crear `lifecycle.ts` por collection con JSDoc + hooks
- Normalizar hooks existentes para usar wrappers `handle*Hook` de `@/shared/handlers`
- Cero cambio de comportamiento, solo reorganizacion y trazabilidad
- Collection por collection

## Fase 1 — Extraer reglas de dominio

- Sacar los `if` de los hooks a `domain/*/rules.ts`
- Cada extraccion es un PR pequeno y aislado

## Fase 2 — Ports + Use Cases para codigo nuevo

- No migrar lo existente — aplicar solo a codigo nuevo
- Crear `domain/errors.ts` y agregar mapeo en `handlerRoute`

## Fase 3 — Migrar use cases existentes

- Mover de `server/useCases/` a `modules/*/domain/useCases/` con ports inyectados
- Migrar cuando ya se toque ese codigo por razon de negocio

## Fase 4 — Hook-first para routes gruesos

- Mover logica de routes como `renders/route.ts` a hooks + use cases
- El route queda thin, el admin ejecuta la misma logica

**Regla: nunca refactorizar por refactorizar. Aplicar el patron cuando ya se este tocando ese codigo.**

---

# 6.1 Convenciones CLEAN validadas por la migracion de uploads

Estas convenciones complementan la guia original y deberian tratarse como reglas operativas del repositorio.

## Shared vs module-local

- `src/shared/**` queda reservado para comportamiento transversal reutilizado por multiples modulos.
- Si una pieza reusable solo pertenece a un feature, debe quedarse dentro de `src/modules/<feature>/**`.
- No mover codigo a `shared` solo porque parece generico; moverlo unicamente cuando exista una necesidad real de reutilizacion entre modulos.

## Ubicacion del feature y fuente de verdad

- Cuando un feature ya tiene un hogar estable en `src/modules/<feature>/**`, esa carpeta pasa a ser la fuente de verdad.
- Cualquier `src/lib/<feature>/**` que siga existiendo debe considerarse deuda transicional de migracion.
- En uploads, la decision es tratar el modulo como fuente de verdad y eliminar facades legacy una vez que ya no sean necesarias.

## Inyeccion de Payload en runtimes nativos

- En hooks, endpoints de Payload, jobs y otros runtimes nativos, se debe preferir `req.payload` en lugar de inicializar un nuevo cliente con `getPayload()`.
- Las dependencias del feature deben soportar inyeccion request-scoped de Payload.
- El bootstrap explicito con `getPayload()` queda solo para contextos donde no exista una instancia de Payload disponible.

## Boundaries y use cases

- Los controllers deben mantenerse delgados.
- Los use cases deben concentrar la orquestacion y exponer una interfaz clara, idealmente mediante clases con `execute()`.
- La logica de negocio no debe vivir en rutas, hooks ni handlers ad hoc.

## DTOs y presenters

- Los DTOs de borde deben definirse con `zod` y tipos inferidos.
- Debe evitarse la validacion manual repetitiva con `typeof` y branching cuando el contrato puede expresarse con schemas.
- Los presenters deben permanecer puros y locales al feature.
- En uploads conviene agrupar presenters por concern, por ejemplo: sesion, upload foreground y upload background.

## Interface vs infrastructure

- Las preocupaciones HTTP, como resolucion de IP o adaptacion de request/response, pertenecen a `interface/http/**`.
- `infrastructure/**` debe contener adapters, stores, clients y config, no logica de borde HTTP.
- Los repositories especificos del feature deben mantenerse dentro de `src/modules/<feature>/infrastructure/**`.

## Naming

- Evitar nombres ambiguos como `shared.ts`, `common.ts` o `utils.ts` dentro de un feature.
- Preferir nombres que declaren responsabilidad, por ejemplo `uploadSchemas`, `uploadAuthorization`, `getUploadApiContext` o `payloadLegacyUploadLookup`.

## Decision concreta observada en uploads

- La migracion de uploads valido que los hooks de coleccion deben delegar en manifiestos de ciclo de vida y use cases del modulo, en vez de mezclar reglas de dominio con detalles de persistencia.
- Tambien valido que el progreso agregado de `UploadSession` debe recomputarse desde servicios del modulo cuando cambian `UploadFile`, manteniendo la logica de negocio en el feature y no en la coleccion.

---

# 7. Riesgos y Mitigaciones

| Riesgo | Impacto | Mitigacion |
| --- | --- | --- |
| Boilerplate excesivo | Medio | Solo crear ports para operaciones con logica real, no CRUD simple |
| Inconsistencia durante migracion | Bajo | Documentar en lifecycle.ts que hooks usan que patron |
| Hooks afterChange fallan silenciosamente | Ya existe | handleAfterChangeHook ya loguea. Agregar alerting en criticos |
| Performance de instanciar adapters | Bajo | Adapters son lightweight (wrappean req.payload) |
| El equipo no adopta el patron | Alto | Empezar con Lifecycle Manifests (bajo costo, alto valor visible) |