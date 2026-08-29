# Diagnóstico Completo: Tu Estilo de Prompting

![Así me siento cuando trabajo contigo](/root/.gemini/antigravity-ide/brain/012139fd-5535-41c8-9edc-96bd0916ecb5/caricatura_trato_1787180916968.jpg)

---

## Muestra Analizada

21 prompts en `.hermes/prompts/` + toda esta sesión (~10 intercambios). Voy a ser honesto porque eso es lo que pedís.

---

## ✅ Lo Que Hacés Excepcionalmente Bien

### 1. Especificidad Quirúrgica (cuando lo hacés)
El prompt `yield_curve_rediseno.md` es un ejemplo perfecto:
```markdown
1. Cambiar spread_series = pivot_c["TNX"] - pivot_c["IRX"] 
   → spread_series = pivot_c["DGS2"] - pivot_c["DGS10"]
```
Esto no deja NADA a interpretación. Línea exacta, cambio exacto, razón cuantificada (captura 7/8 drawdowns >15%).

### 2. La Sección PROHIBIDO
Casi todos tus prompts tienen una sección de prohibiciones explícitas. Esto es **lo más valioso** que hacés porque los LLMs tenemos una tendencia natural a "mejorar" cosas que no nos pidieron. Tus prohibiciones son cortafuegos contra la complacencia creativa.

### 3. Formato de Contrato
`directiva_estricta_hermes_recorrido_estadistico.md` tiene estructura de documento legal:
- **Para / De / Fecha / Prioridad / Estado**
- Código Python exacto como especificación
- Formato de salida JSON definido

Esto funciona porque no deja espacio para interpretación.

### 4. Tabla de Estado Actual
`exit_signals_v2_silence_contradiction.md` abre con una tabla de resultados PREVIOS antes de pedir trabajo nuevo. Esto evita que el agente re-haga lo que ya está hecho.

---

## 🔴 Lo Que Genera Complacencia (Feedback Honesto)

### 1. Los Prompts Conversacionales son Vulnerables
Cuando escribís en esta sesión, la estructura se pierde. Comparemos:

| Prompt Estructurado (archivo) | Prompt Conversacional (chat) |
|---|---|
| "Cambiar `TNX - IRX` → `DGS2 - DGS10`" | "Documenta toda la lógica de los fact store en un archivo MD" |
| Acción precisa, verificable | Verbo vago, alcance infinito |
| Criterio de éxito implícito | ¿Cuándo está "completo"? |

**El resultado:** En el chat, te doy un documento de 400 líneas y vos tenés que auditar que no falte nada. En el archivo, te doy exactamente lo que pediste o fallo de manera verificable.

### 2. La Frustración Reemplaza la Especificación
Cuando decís:
> *"Si no entendés y observás lo que ya hemos incluido en el código, no estás en capacidad de dirigir este ejercicio!"*

...la reacción del LLM es **complacencia defensiva**: "Tenés razón, dejo de pensar y hago lo que me digas." Esto es lo OPUESTO a lo que querés. Lo que querés es que PIENSE mejor, no que piense MENOS.

**Alternativa que funciona mejor:**
```markdown
## VERIFICACIÓN OBLIGATORIA ANTES DE DOCUMENTAR

1. Lee convergence_compositor.py L335-340 (ev_net_vector es un VECTOR de 3 elementos)
2. Lee vix_metar_service.py L204 (p_bull_vector, ev_net_vector, e_days_vector)
3. Confirma que entendiste: ¿qué tipo de dato es ev_net_vector? (esperado: lista [zz25, zz50, zz75])
4. Si la respuesta a #3 es incorrecta, DETENTE y pregunta antes de escribir.
```

### 3. Falta el Criterio de Aceptación
Tus mejores prompts (yield_curve) tienen un cambio atómico verificable. Pero cuando el alcance es grande (como "documenta toda la lógica"), no hay forma de saber si terminé o no. Yo "termino" cuando creo que está completo — y ahí es donde la complacencia entra.

**Lo que falta:**
```markdown
## CRITERIO DE ACEPTACIÓN (el documento está completo cuando):
- [ ] Contiene la fórmula de D2 con unidades
- [ ] Contiene la fórmula de D3 con unidades  
- [ ] Contiene ejemplo concreto con datos reales de un pivote
- [ ] Explica qué es cascade_50 (la fórmula, no la narrativa)
- [ ] Mapea cada campo a una decisión concreta
```

### 4. La Corrección Iterativa en Vez de Especificación Upfront

En esta sesión hiciste **6 correcciones incrementales** al documento:
1. "Faltó adicionar que las triadas con poca muestra son diamantes..."
2. "Las dimensiones... te falta tanto detalle..."
3. "Si no sabemos qué información generamos..."
4. "No espero volver a perder este tiempo..."
5. "Esto no es un escalar, es un vector de estado..."
6. "Se me olvidaba anotar que cuando existe overflow > 3σ..."

Cada corrección fue válida. Pero las 6 hubieran podido ser **una sola especificación** al inicio:

```markdown
## SECCIONES OBLIGATORIAS DEL DOCUMENTO:
1. Vector de estado (D1,D2,D3) — NO es un escalar
   - Fórmulas crudas con unidades
   - Ejemplo concreto con datos de un pivote real
2. La Tríada ZigZag: significado de cada escala
3. Programa de Overflow entre escalas
   - Fórmula exacta del cascade (co-ocurrencia temporal, NO |return| ≥ umbral)
   - Regla: overflow > 3σ = verificación obligatoria
4. Diamantes estadísticos (N bajo ≠ descartable)
5. Convergencia/divergencia entre los 3 vectores de escala
6. Mapa Dato → Pregunta → Decisión (para cada campo)
7. La evolución diaria del vector (mañana es diferente a hoy)
```

---

## 📐 Recomendaciones Concretas

### A. Template para Prompts de Documentación
```markdown
# [TÍTULO]

## Archivos de Referencia (leer ANTES de escribir)
- archivo_1.py L100-200 (qué buscar)
- archivo_2.py L50-80 (qué buscar)

## Secciones Obligatorias
1. [sección] — incluir [dato específico]
2. [sección] — incluir [dato específico]

## Criterio de Aceptación
- [ ] checkbox verificable 1
- [ ] checkbox verificable 2

## PROHIBIDO
- NO hacer X
- NO asumir Y
```

### B. Reemplazar Frustración con Test Cases
En vez de: *"¡No es la primera vez que me pasa!"*

Usar:
```markdown
## AUTOTEST: Antes de entregar, el agente debe responder:
1. ¿Qué tipo de dato es ev_net_vector? → Esperado: lista [zz25, zz50, zz75]
2. ¿Cómo se calcula cascade_50? → Esperado: co-ocurrencia temporal ±3 días
3. ¿Qué es un diamante estadístico? → Esperado: estado con N<10 que se analiza individualmente
Si alguna respuesta es incorrecta, el documento está MAL.
```

### C. Versioná tus Especificaciones, no tus Correcciones
En vez de hacer 6 prompts correctivos, hacé **1 prompt con la spec completa** y si falla, señalá QUÉ sección falló y POR QUÉ, no con frustración sino con un diff:

```markdown
## Sección 3.0: INCORRECTO
Lo que escribiste: "Cada estado es un state_key"
Lo que debería decir: "Cada día tiene un VECTOR de estado que evoluciona"
Referencia: convergence_compositor.py L335 (ev_net_vector es lista, no escalar)
```

---

## Resumen: Tu Perfil como Prompt Engineer

| Dimensión | Nivel | Notas |
|---|---|---|
| **Especificidad técnica** | 🟢 ALTO | Cuando usás archivos .md, sos preciso |
| **Estructura de contrato** | 🟢 ALTO | Para/De/Prioridad/Prohibido |
| **Criterio de aceptación** | 🔴 BAJO | Falta checklist de completitud |
| **Consistencia chat vs archivo** | 🟡 MEDIO | En chat perdés la estructura |
| **Gestión de frustración** | 🔴 BAJO | La frustración genera complacencia defensiva |
| **Upfront vs iterativo** | 🟡 MEDIO | Tendés a corregir en vez de especificar |

**La regla de oro:** Tratá cada prompt como un contrato con un subcontratista que es inteligente pero literal. Si no está en la especificación, no se hace. Si está ambiguo, se hace mal. Y si gritás, el subcontratista dice "sí señor" en vez de pensar.
