# Motor de Regímenes de Mercado — Investigación y Ejercicios Probatorios

Directorio de investigación para el diseño empírico del **MarketRegimeEngine**.

## Contexto

La propuesta original (Flash, 30-Ago-2026) definió un Motor de Regímenes con 4 dimensiones
(Cinemática, Amplitud, Volatilidad, Macro) y 5 regímenes operacionales. La auditoría
arquitectónica (Opus, 31-Ago-2026) identificó que las fronteras de estos regímenes son
narrativas, no empíricas, y propuso 6 ejercicios probatorios para construir desde los datos.

## Archivos

| Archivo | Contenido |
|:---|:---|
| `auditoria_arquitectonica_motor_regimenes.md` | Auditoría de la propuesta, 6 debilidades, 6 ejercicios probatorios |

## Ejercicios Probatorios Pendientes

1. **E1:** Descubrimiento no-supervisado de regímenes naturales (clustering D1 vector)
2. **E2:** Retornos forward condicionales por régimen descubierto
3. **E3:** Matriz de coincidencia señal ↔ régimen
4. **E4:** σ-Overflow como detector de transición de régimen
5. **E5:** Persistencia y duración (Matriz de Transición de Markov)
6. **E6:** Cascade conviction como precursor de agotamiento

## Dependencias

- `data/research/continuous_metar_lake.parquet` (8,453 días × 257 features)
- `data/research/signals/validacion_oos_catalogo_v7.json` (señales validadas OOS)
- `backend/modules/entry_decision/domain/rules/*_fact_store.json` (11 fact stores)

## Orden de Ejecución

E1 → E2 → E5 → E4 → E3 → E6
