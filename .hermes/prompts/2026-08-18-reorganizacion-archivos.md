# PROMPT PARA GEMINI — Reorganización de Archivos y Taxonomía

## OBJETIVO
Reorganizar la estructura de archivos de análisis siguiendo Clean Architecture. NO implementar código ni señales de EXIT.

## CONTEXTO
Actualmente tenemos archivos de análisis en `scratch/` que deben moverse a `backend/modules/entry_decision/references/` siguiendo la metodología del proyecto.

## ARCHIVOS A REORGANIZAR

### 1. Análisis de Señales de EXIT
**Origen:** `scratch/analisis_señales_exit.md` y `scratch/replanteamiento_señales_exit.md`
**Destino:** `backend/modules/entry_decision/references/señales-exit.md`

**Acción:**
- Crear el archivo `señales-exit.md` en el destino
- Consolidar el contenido de ambos archivos de origen
- NO eliminar los archivos originales (los mantendremos hasta validar)

### 2. Análisis Estadístico Profundo
**Origen:** `scratch/analisis_estadistico_profundo.md`
**Destino:** `backend/modules/entry_decision/references/cascade-conviction.md`

**Acción:**
- Crear el archivo `cascade-conviction.md` en el destino
- Mover el contenido del archivo de origen
- NO eliminar el archivo original hasta validar

### 3. Índice de Documentación
**Destino:** `backend/references/README.md`

**Acción:**
- Crear el archivo README.md
- Generar índice de toda la documentación técnica del backend
- Incluir enlaces a los archivos de references/

## ESTRUCTURA FINAL

```
botero-trade/
├── backend/
│   ├── modules/entry_decision/
│   │   └── references/
│   │       ├── señales-exit.md          # NUEVO
│   │       ├── cascade-conviction.md    # NUEVO
│   │       └── [otros archivos existentes]
│   └── references/
│       └── README.md                    # NUEVO (índice)
└── scratch/
    ├── analisis_señales_exit.md         # MANTENER (hasta validar)
    ├── replanteamiento_señales_exit.md  # MANTENER (hasta validar)
    └── analisis_estadistico_profundo.md # MANTENER (hasta validar)
```

## CONTENIDO DE LOS ARCHIVOS

### señales-exit.md
Debe incluir:
- Contexto del problema (11 señales ENTRY, solo 2 EXIT)
- Hallazgos clave (bsi_recovery es efectiva, las de pánico son ENTRY)
- Señales de EXIT propuestas
- Criterios de éxito
- Próximos pasos

### cascade-conviction.md
Debe incluir:
- Marco de Edge Defensivo
- Análisis por década
- Sign-flips D2×D3
- Precursores de crash
- Resultados de validación

### README.md
Debe incluir:
- Índice de toda la documentación técnica
- Enlaces a archivos de references/
- Descripción breve de cada documento

## VERIFICACIÓN

```bash
# Verificar que los archivos se crearon correctamente
ls -la backend/modules/entry_decision/references/
ls -la backend/references/

# Verificar que los archivos originales aún existen
ls -la scratch/analisis_señales_exit.md
ls -la scratch/replanteamiento_señales_exit.md
ls -la scratch/analisis_estadistico_profundo.md

# Verificar que el README.md se creó
cat backend/references/README.md
```

## PROHIBIDO
- ❌ NO implementar código en exit_signals.py
- ❌ NO modificar medir_senal.py
- ❌ NO crear señales de EXIT
- ❌ NO eliminar archivos de scratch/
- ❌ NO modificar señales de ENTRY existentes
- ❌ NO modificar cascade_conviction

## ENTREGABLES
1. `backend/modules/entry_decision/references/señales-exit.md` (creado)
2. `backend/modules/entry_decision/references/cascade-conviction.md` (creado)
3. `backend/references/README.md` (creado)

## FIRMA
qwen3.7-plus (Hermes)
18-Ago-2026
