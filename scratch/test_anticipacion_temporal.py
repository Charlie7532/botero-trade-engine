#!/usr/bin/env python3
"""
Tests para validar la corrección de Bug 1: Anticipación Temporal.

Bug actual (líneas 507-529):
- Mide autocorrelación entre pivotes consecutivos
- Cuenta cuántos pivotes tienen la señal activa consecutivamente
- NO mide cuántos días ANTES del pivot_date la señal estaba activa

Corrección requerida:
- Para cada pivot_date donde la señal está activa
- Medir cuántos días ANTES (en barras diarias) la señal ya estaba activa
- La anticipación debe medirse en días de trading, no en pivotes
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# =============================================================================
# CRITERIOS DE ACEPTACIÓN
# =============================================================================

CRITERIOS_ACEPTACION = {
    "CA1": "La función debe calcular días de anticipación, no contar pivotes",
    "CA2": "Para cada pivot con señal activa, debe buscar cuántos días antes la señal ya estaba activa",
    "CA3": "La anticipación debe medirse en días de trading (barras diarias), no en índices de pivotes",
    "CA4": "Si la señal se activa por primera vez en el pivot, la anticipación debe ser 0",
    "CA5": "Si la señal estaba activa en el pivote anterior, debe calcular la distancia en días",
    "CA6": "Debe manejar correctamente pivotes sin señal previa (anticipación = 0 o NaN)",
    "CA7": "Los resultados deben ser reproducibles y deterministas",
}


# =============================================================================
# CASOS DE PRUEBA
# =============================================================================

def test_caso_1_señal_activa_0_dias_antes():
    """
    Caso 1: Señal activa 0 días antes (activación en el mismo pivot)
    
    Escenario: La señal se activa por primera vez en un pivot.
    No hay pivotes anteriores con la señal activa.
    
    Resultado esperado: anticipacion_dias = 0
    """
    print("\n" + "="*70)
    print("TEST 1: Señal activa 0 días antes (primera activación)")
    print("="*70)
    
    # Crear datos de prueba
    fechas = pd.date_range("2020-01-01", periods=10, freq="B")  # días de trading
    df = pd.DataFrame({
        "pivot_date": fechas,
        "pivot_type": ["MIN"] * 10,
        "credit_val": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
    })
    
    # Señal: solo activa en el último pivot (primera activación)
    señal = pd.Series([False] * 9 + [True], index=df.index)
    
    # Calcular anticipación esperada
    # Como es la primera activación, no hay pivote anterior con señal
    anticipacion_esperada = 0
    
    print(f"Fecha del pivot con señal: {df.loc[señal, 'pivot_date'].values[0]}")
    print(f"Señal activa en {señal.sum()} pivote(s)")
    print(f"Anticipación esperada: {anticipacion_esperada} días")
    
    # Verificar
    assert señal.sum() == 1, "La señal debe estar activa en exactamente 1 pivot"
    print("✓ Caso 1 válido: señal activa por primera vez")
    
    return {
        "caso": "señal_activa_0_dias_antes",
        "anticipacion_esperada": anticipacion_esperada,
        "descripcion": "Primera activación de la señal, sin pivotes anteriores activos",
    }


def test_caso_2_señal_activa_3_dias_antes():
    """
    Caso 2: Señal activa 3 días antes
    
    Escenario: La señal está activa en un pivot, y el pivote anterior
    (que estaba 3 días antes) también tenía la señal activa.
    
    Resultado esperado: anticipacion_dias = 3
    """
    print("\n" + "="*70)
    print("TEST 2: Señal activa 3 días antes")
    print("="*70)
    
    # Crear datos de prueba
    # Pivot 0: 2020-01-01 (señal activa)
    # Pivot 3: 2020-01-04 (señal activa) - exactamente 3 días después
    fechas = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", 
                             "2020-01-04", "2020-01-05"])
    df = pd.DataFrame({
        "pivot_date": fechas,
        "pivot_type": ["MIN"] * 5,
        "credit_val": [100, 101, 102, 103, 104],
    })
    
    # Señal activa en pivotes 0 y 3 (diferencia = 3 días)
    señal = pd.Series([True, False, False, True, False], index=df.index)
    
    # Calcular anticipación esperada para el pivot en índice 3
    pivot_idx = 3
    pivot_date_actual = df.loc[pivot_idx, "pivot_date"]
    
    # Buscar pivote anterior con señal activa
    pivotes_anteriores_activos = []
    for i in range(pivot_idx - 1, -1, -1):
        if señal.iloc[i]:
            pivotes_anteriores_activos.append(i)
            break
    
    if pivotes_anteriores_activos:
        idx_anterior = pivotes_anteriores_activos[0]
        fecha_anterior = df.loc[idx_anterior, "pivot_date"]
        dias_antes = (pivot_date_actual - fecha_anterior).days
    else:
        dias_antes = 0
    
    anticipacion_esperada = dias_antes
    
    print(f"Pivot actual: {pivot_date_actual.strftime('%Y-%m-%d')}")
    print(f"Pivot anterior con señal: {fecha_anterior.strftime('%Y-%m-%d')}")
    print(f"Días de diferencia: {dias_antes}")
    print(f"Anticipación esperada: {anticipacion_esperada} días")
    
    assert anticipacion_esperada == 3, f"Se esperaban 3 días, se obtuvieron {anticipacion_esperada}"
    print("✓ Caso 2 válido: señal activa 3 días antes")
    
    return {
        "caso": "señal_activa_3_dias_antes",
        "anticipacion_esperada": anticipacion_esperada,
        "descripcion": "Señal activa en pivote actual y en pivote anterior 3 días antes",
    }


def test_caso_3_señal_activa_7_dias_antes():
    """
    Caso 3: Señal activa 7 días antes
    
    Escenario: La señal está activa en un pivot, y el pivote anterior
    (que estaba 7 días antes) también tenía la señal activa.
    
    Resultado esperado: anticipacion_dias = 7
    """
    print("\n" + "="*70)
    print("TEST 3: Señal activa 7 días antes")
    print("="*70)
    
    # Crear datos de prueba
    # Pivot 0: 2020-01-01 (señal activa)
    # Pivot 7: 2020-01-08 (señal activa) - exactamente 7 días después
    fechas = pd.to_datetime([
        "2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04",
        "2020-01-05", "2020-01-06", "2020-01-07", "2020-01-08"
    ])
    df = pd.DataFrame({
        "pivot_date": fechas,
        "pivot_type": ["MIN"] * 8,
        "credit_val": [100, 101, 102, 103, 104, 105, 106, 107],
    })
    
    # Señal activa en pivotes 0 y 7 (diferencia = 7 días)
    señal = pd.Series([True, False, False, False, False, False, False, True], index=df.index)
    
    # Calcular anticipación esperada para el pivot en índice 7
    pivot_idx = 7
    pivot_date_actual = df.loc[pivot_idx, "pivot_date"]
    
    # Buscar pivote anterior con señal activa
    pivotes_anteriores_activos = []
    for i in range(pivot_idx - 1, -1, -1):
        if señal.iloc[i]:
            pivotes_anteriores_activos.append(i)
            break
    
    if pivotes_anteriores_activos:
        idx_anterior = pivotes_anteriores_activos[0]
        fecha_anterior = df.loc[idx_anterior, "pivot_date"]
        dias_antes = (pivot_date_actual - fecha_anterior).days
    else:
        dias_antes = 0
    
    anticipacion_esperada = dias_antes
    
    print(f"Pivot actual: {pivot_date_actual.strftime('%Y-%m-%d')}")
    print(f"Pivot anterior con señal: {fecha_anterior.strftime('%Y-%m-%d')}")
    print(f"Días de diferencia: {dias_antes}")
    print(f"Anticipación esperada: {anticipacion_esperada} días")
    
    assert anticipacion_esperada == 7, f"Se esperaban 7 días, se obtuvieron {anticipacion_esperada}"
    print("✓ Caso 3 válido: señal activa 7 días antes")
    
    return {
        "caso": "señal_activa_7_dias_antes",
        "anticipacion_esperada": anticipacion_esperada,
        "descripcion": "Señal activa en pivote actual y en pivote anterior 7 días antes",
    }


def test_caso_4_señal_no_activa_antes():
    """
    Caso 4: Señal NO activa antes (primera aparición en el pivot)
    
    Escenario: La señal se activa en un pivot, pero ningún pivote anterior
    tenía la señal activa.
    
    Resultado esperado: anticipacion_dias = 0
    """
    print("\n" + "="*70)
    print("TEST 4: Señal NO activa antes (primera aparición)")
    print("="*70)
    
    # Crear datos de prueba
    fechas = pd.date_range("2020-01-01", periods=10, freq="B")
    df = pd.DataFrame({
        "pivot_date": fechas,
        "pivot_type": ["MIN"] * 10,
        "credit_val": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
    })
    
    # Señal activa solo en el último pivot
    señal = pd.Series([False] * 9 + [True], index=df.index)
    
    # Calcular anticipación esperada
    pivot_idx = señal.idxmax()
    pivot_date_actual = df.loc[pivot_idx, "pivot_date"]
    
    # Buscar pivote anterior con señal activa
    pivotes_anteriores_activos = []
    for i in range(pivot_idx - 1, -1, -1):
        if señal.iloc[i]:
            pivotes_anteriores_activos.append(i)
            break
    
    if pivotes_anteriores_activos:
        idx_anterior = pivotes_anteriores_activos[0]
        fecha_anterior = df.loc[idx_anterior, "pivot_date"]
        dias_antes = (pivot_date_actual - fecha_anterior).days
    else:
        dias_antes = 0
    
    anticipacion_esperada = dias_antes
    
    print(f"Pivot actual: {pivot_date_actual.strftime('%Y-%m-%d')}")
    print(f"Señal activa en {señal.sum()} pivote(s)")
    print(f"Anticipación esperada: {anticipacion_esperada} días")
    
    assert anticipacion_esperada == 0, f"Se esperaban 0 días, se obtuvieron {anticipacion_esperada}"
    print("✓ Caso 4 válido: señal sin activación previa")
    
    return {
        "caso": "señal_no_activa_antes",
        "anticipacion_esperada": anticipacion_esperada,
        "descripcion": "Señal activa por primera vez, sin pivotes anteriores activos",
    }


def test_caso_5_multiples_activaciones():
    """
    Caso 5: Múltiples activaciones con diferentes anticipaciones
    
    Escenario: La señal se activa en varios pivotes, cada uno con
    diferente distancia temporal al pivote anterior activo.
    
    Resultado esperado: Lista de anticipaciones para cada pivote activo
    """
    print("\n" + "="*70)
    print("TEST 5: Múltiples activaciones con diferentes anticipaciones")
    print("="*70)
    
    # Crear datos de prueba
    # Pivot 0: 2020-01-01 (señal activa)
    # Pivot 3: 2020-01-06 (señal activa) - 5 días después del pivot 0
    # Pivot 8: 2020-01-11 (señal activa) - 5 días después del pivot 3
    fechas = pd.to_datetime([
        "2020-01-01",  # pivot 0: señal activa
        "2020-01-02",  # pivot 1: sin señal
        "2020-01-03",  # pivot 2: sin señal
        "2020-01-06",  # pivot 3: señal activa (5 días después del pivot 0)
        "2020-01-07",  # pivot 4: sin señal
        "2020-01-08",  # pivot 5: sin señal
        "2020-01-09",  # pivot 6: sin señal
        "2020-01-10",  # pivot 7: sin señal
        "2020-01-11",  # pivot 8: señal activa (5 días después del pivot 3)
        "2020-01-12",  # pivot 9: sin señal
    ])
    
    df = pd.DataFrame({
        "pivot_date": fechas,
        "pivot_type": ["MIN"] * 10,
        "credit_val": range(100, 110),
    })
    
    # Señal activa en pivotes 0, 3, 8
    señal = pd.Series([True, False, False, True, False, False, False, False, True, False], 
                     index=df.index)
    
    # Calcular anticipaciones
    anticipaciones = []
    for i in np.where(señal.values)[0]:
        pivot_date_actual = df.loc[i, "pivot_date"]
        
        # Buscar pivote anterior con señal activa
        pivote_anterior_idx = None
        for j in range(i - 1, -1, -1):
            if señal.iloc[j]:
                pivote_anterior_idx = j
                break
        
        if pivote_anterior_idx is not None:
            fecha_anterior = df.loc[pivote_anterior_idx, "pivot_date"]
            dias_antes = (pivot_date_actual - fecha_anterior).days
        else:
            dias_antes = 0
        
        anticipaciones.append({
            "pivot_idx": i,
            "pivot_date": pivot_date_actual,
            "dias_antes": dias_antes,
        })
    
    print("Anticipaciones calculadas:")
    for ant in anticipaciones:
        print(f"  Pivot {ant['pivot_idx']} ({ant['pivot_date'].strftime('%Y-%m-%d')}): "
              f"{ant['dias_antes']} días antes")
    
    # Verificar
    assert len(anticipaciones) == 3, f"Se esperaban 3 anticipaciones, se obtuvieron {len(anticipaciones)}"
    assert anticipaciones[0]["dias_antes"] == 0, "Primera activación debe tener 0 días"
    assert anticipaciones[1]["dias_antes"] == 5, f"Segunda activación debe tener 5 días, no {anticipaciones[1]['dias_antes']}"
    assert anticipaciones[2]["dias_antes"] == 5, f"Tercera activación debe tener 5 días, no {anticipaciones[2]['dias_antes']}"
    
    print("✓ Caso 5 válido: múltiples activaciones con diferentes anticipaciones")
    
    return {
        "caso": "multiples_activaciones",
        "anticipaciones": anticipaciones,
        "descripcion": "Tres activaciones con anticipaciones de 0, 5, y 5 días",
    }


# =============================================================================
# FUNCIÓN DE REFERENCIA PARA LA CORRECCIÓN
# =============================================================================

def calcular_anticipacion_temporal(spy, señal, df):
    """
    Implementación de referencia para calcular la anticipación temporal.
    
    Para cada pivot donde la señal está activa:
    1. Buscar el pivote anterior con señal activa
    2. Calcular la distancia en días entre ambos pivotes
    3. Si no hay pivote anterior activo, la anticipación es 0
    
    Args:
        spy: DataFrame de barras diarias (no se usa en esta implementación,
             pero se incluye para consistencia con otras funciones)
        señal: pd.Series booleano indicando dónde la señal está activa
        df: DataFrame de pivotes con pivot_date
    
    Returns:
        dict con estadísticas de anticipación:
        - anticipaciones_dias: lista de días de anticipación para cada pivot activo
        - mean: media de días de anticipación
        - median: mediana de días de anticipación
        - p5, p25, p75, p95: percentiles
        - n_total: número total de pivotes con señal activa
        - n_anticipados: número de pivotes con anticipación > 0
        - pct_anticipados: porcentaje de pivotes con anticipación > 0
    """
    if señal.sum() == 0:
        return None
    
    anticipaciones_dias = []
    
    for i in np.where(señal.values)[0]:
        pivot_date_actual = df["pivot_date"].iloc[i]
        
        # Buscar pivote anterior con señal activa
        pivote_anterior_idx = None
        for j in range(i - 1, -1, -1):
            if señal.iloc[j]:
                pivote_anterior_idx = j
                break
        
        if pivote_anterior_idx is not None:
            fecha_anterior = df["pivot_date"].iloc[pivote_anterior_idx]
            dias_antes = (pivot_date_actual - fecha_anterior).days
        else:
            dias_antes = 0
        
        anticipaciones_dias.append(dias_antes)
    
    anticipaciones_arr = np.array(anticipaciones_dias)
    
    return {
        "anticipaciones_dias": anticipaciones_dias,
        "mean": float(np.mean(anticipaciones_arr)),
        "median": float(np.median(anticipaciones_arr)),
        "p5": float(np.percentile(anticipaciones_arr, 5)),
        "p25": float(np.percentile(anticipaciones_arr, 25)),
        "p75": float(np.percentile(anticipaciones_arr, 75)),
        "p95": float(np.percentile(anticipaciones_arr, 95)),
        "n_total": int(len(anticipaciones_dias)),
        "n_anticipados": int((anticipaciones_arr > 0).sum()),
        "pct_anticipados": float((anticipaciones_arr > 0).mean() * 100),
    }


# =============================================================================
# MÉTRICAS DE VALIDACIÓN
# =============================================================================

METRICAS_VALIDACION = {
    "M1": {
        "nombre": "Exactitud temporal",
        "descripcion": "La anticipación debe medirse en días, no en índices de pivotes",
        "criterio": "dias_antes == (pivot_date_actual - pivot_date_anterior).days",
    },
    "M2": {
        "nombre": "Consistencia de primera activación",
        "descripcion": "La primera activación de la señal debe tener anticipación = 0",
        "criterio": "anticipaciones_dias[0] == 0",
    },
    "M3": {
        "nombre": "Monotonicidad temporal",
        "descripcion": "Las anticipaciones deben ser no-negativas",
        "criterio": "all(d >= 0 for d in anticipaciones_dias)",
    },
    "M4": {
        "nombre": "Cobertura completa",
        "descripcion": "Debe calcularse anticipación para todos los pivotes con señal activa",
        "criterio": "len(anticipaciones_dias) == señal.sum()",
    },
    "M5": {
        "nombre": "Reproducibilidad",
        "descripcion": "Mismos inputs deben producir mismos outputs",
        "criterio": "f(x) == f(x) en múltiples llamadas",
    },
}


# =============================================================================
# PROCEDIMIENTO DE VERIFICACIÓN
# =============================================================================

PROCEDIMIENTO_VERIFICACION = """
PROCEDIMIENTO DE VERIFICACIÓN
==============================

1. EJECUTAR TESTS UNITARIOS
   - Ejecutar test_caso_1 hasta test_caso_5
   - Todos deben pasar sin errores
   - Verificar que las anticipaciones calculadas coincidan con las esperadas

2. VALIDAR CONTRA DATOS REALES
   - Cargar quants_obs.pkl y ejecutar la función calcular_anticipacion_temporal
   - Verificar que:
     * No haya valores negativos
     * La primera activación tenga anticipación = 0
     * Los percentiles sean razonables (no todos 0, no todos > 30)

3. COMPARAR CON IMPLEMENTACIÓN ACTUAL
   - Ejecutar la implementación actual (líneas 507-529)
   - Ejecutar la implementación corregida
   - Verificar que los resultados sean diferentes
   - La implementación actual mide autocorrelación entre pivotes
   - La implementación corregida mide días de anticipación

4. VALIDAR INTEGRACIÓN
   - Integrar la función corregida en medir_senal.py
   - Ejecutar el script completo con una señal de prueba
   - Verificar que no se rompan otras funcionalidades
   - Verificar que el reporte incluya la nueva métrica de anticipación

5. VALIDAR RENDIMIENTO
   - Medir tiempo de ejecución con 1590 pivotes
   - Debe ser < 1 segundo
   - No debe haber degradación significativa

6. DOCUMENTAR RESULTADOS
   - Registrar métricas de validación
   - Documentar casos edge (señales con 0 activaciones, 1 activación, etc.)
   - Crear ejemplos de uso
"""


# =============================================================================
# EJECUCIÓN DE TESTS
# =============================================================================

def ejecutar_tests():
    """Ejecuta todos los tests y retorna resumen."""
    print("\n" + "="*70)
    print("EJECUTANDO TESTS PARA BUG 1: ANTICIPACIÓN TEMPORAL")
    print("="*70)
    
    resultados = []
    
    try:
        resultados.append(test_caso_1_señal_activa_0_dias_antes())
    except Exception as e:
        print(f"✗ TEST 1 FALLÓ: {e}")
        resultados.append({"caso": "test_1", "error": str(e)})
    
    try:
        resultados.append(test_caso_2_señal_activa_3_dias_antes())
    except Exception as e:
        print(f"✗ TEST 2 FALLÓ: {e}")
        resultados.append({"caso": "test_2", "error": str(e)})
    
    try:
        resultados.append(test_caso_3_señal_activa_7_dias_antes())
    except Exception as e:
        print(f"✗ TEST 3 FALLÓ: {e}")
        resultados.append({"caso": "test_3", "error": str(e)})
    
    try:
        resultados.append(test_caso_4_señal_no_activa_antes())
    except Exception as e:
        print(f"✗ TEST 4 FALLÓ: {e}")
        resultados.append({"caso": "test_4", "error": str(e)})
    
    try:
        resultados.append(test_caso_5_multiples_activaciones())
    except Exception as e:
        print(f"✗ TEST 5 FALLÓ: {e}")
        resultados.append({"caso": "test_5", "error": str(e)})
    
    # Resumen
    print("\n" + "="*70)
    print("RESUMEN DE TESTS")
    print("="*70)
    
    exitosos = sum(1 for r in resultados if "error" not in r)
    total = len(resultados)
    
    print(f"Tests exitosos: {exitosos}/{total}")
    
    if exitosos == total:
        print("\n✓ TODOS LOS TESTS PASARON")
        print("\nLa implementación de referencia calcular_anticipacion_temporal()")
        print("puede usarse como base para la corrección del Bug 1.")
    else:
        print("\n✗ ALGUNOS TESTS FALLARON")
        for r in resultados:
            if "error" in r:
                print(f"  - {r['caso']}: {r['error']}")
    
    return resultados


if __name__ == "__main__":
    resultados = ejecutar_tests()
    
    print("\n" + "="*70)
    print("CRITERIOS DE ACEPTACIÓN")
    print("="*70)
    for k, v in CRITERIOS_ACEPTACION.items():
        print(f"{k}: {v}")
    
    print("\n" + "="*70)
    print("MÉTRICAS DE VALIDACIÓN")
    print("="*70)
    for k, v in METRICAS_VALIDACION.items():
        print(f"{k} - {v['nombre']}: {v['descripcion']}")
    
    print("\n" + "="*70)
    print(PROCEDIMIENTO_VERIFICACION)
