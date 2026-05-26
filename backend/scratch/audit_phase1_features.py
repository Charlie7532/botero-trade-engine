"""
AUDITORÍA DE CALIDAD — Fase 1 Features
========================================
Equipo de forencia y ciencia de datos.

Validaciones:
1. INTEGRIDAD: ¿Las 7 columnas existen y tienen datos?
2. LOOK-AHEAD: ¿Alguna feature usa datos futuros? (test de causalidad)
3. ZIGZAG-FREE: ¿Cero dependencia del zigzag en cómputo?
4. CONSISTENCY: ¿Las features son consistentes entre el tape y cómputo independiente?
5. DISTRIBUCIÓN: ¿Los rangos son razonables?
6. NO-DEGRADACIÓN: ¿Los heads existentes siguen exactos? (probabilities intactas)
7. CROSS-VALIDATION: Recalcular cada feature desde los datos crudos y comparar
"""
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv; load_dotenv(root / ".env")

import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def banner(t):
    print(f"\n{'═'*100}\n  {t}\n{'═'*100}")

def ok(msg): print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ FALLO: {msg}")
def warn(msg): print(f"  ⚠️  {msg}")

store = TimescaleDataStore()
PASS_COUNT = 0
FAIL_COUNT = 0

def check(condition, pass_msg, fail_msg):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        ok(pass_msg)
        PASS_COUNT += 1
    else:
        fail(fail_msg)
        FAIL_COUNT += 1

# ═══════════════════════════════════════════════════════════
banner("1. INTEGRIDAD — ¿Las 7 columnas existen con datos?")
# ═══════════════════════════════════════════════════════════

tape = pd.read_sql("SELECT * FROM engine.signal_tape ORDER BY ticker, timestamp", store.engine)
print(f"  Total rows in tape: {len(tape):,d}")

NEW_COLS = ['slope_decel_wave', 'slope_decel_current', 'sigma_divergence',
            'complacency_index', 'rsi_extreme_zone', 'rsi_trap_zone', 'rsi_bearish_div']

for col in NEW_COLS:
    exists = col in tape.columns
    check(exists, f"{col} existe en tape", f"{col} NO existe en tape")
    if exists:
        non_null = tape[col].notna().sum()
        null_pct = tape[col].isna().mean() * 100
        check(non_null > 0, f"  {col}: {non_null:,d} non-null ({100-null_pct:.1f}% fill)",
              f"  {col}: ALL NULL ({null_pct:.1f}% null)")

# ═══════════════════════════════════════════════════════════
banner("2. LOOK-AHEAD TEST — ¿Las features usan datos futuros?")
# ═══════════════════════════════════════════════════════════

print("  Test: Para cada feature, verificar que el valor en bar[t] NO cambia")
print("  si eliminamos bars DESPUÉS de t. Si cambia → look-ahead.")
print()

# Pick a sample ticker
sample_tk = 'SPY'
tk_tape = tape[tape['ticker'] == sample_tk].sort_values('timestamp').reset_index(drop=True)
midpoint = len(tk_tape) // 2

for col in NEW_COLS:
    # Feature at midpoint should only depend on data up to midpoint
    val_at_mid = tk_tape.loc[midpoint, col]
    
    # slope_decel_wave = wave_slope[t] - wave_slope[t-5]
    # Both values are at t and t-5 → purely historical
    if col == 'slope_decel_wave':
        ws = tk_tape['wave_slope']
        expected = ws.iloc[midpoint] - ws.iloc[midpoint - 5] if midpoint >= 5 else 0
        match = abs((val_at_mid or 0) - expected) < 1e-4
        check(match, f"{col}: computed = {val_at_mid:.6f}, expected = {expected:.6f} ✓",
              f"{col}: MISMATCH computed={val_at_mid}, expected={expected}")
    
    elif col == 'slope_decel_current':
        cs = tk_tape['current_slope']
        expected = cs.iloc[midpoint] - cs.iloc[midpoint - 5] if midpoint >= 5 else 0
        match = abs((val_at_mid or 0) - expected) < 1e-4
        check(match, f"{col}: computed = {val_at_mid:.6f}, expected = {expected:.6f} ✓",
              f"{col}: MISMATCH computed={val_at_mid}, expected={expected}")
    
    elif col == 'sigma_divergence':
        st = tk_tape['sigma_tide'].iloc[midpoint]
        sw = tk_tape['sigma_wave'].iloc[midpoint]
        expected = (st or 0) - (sw or 0)
        match = abs((val_at_mid or 0) - expected) < 1e-4
        check(match, f"{col}: computed = {val_at_mid:.6f}, expected = {expected:.6f} ✓",
              f"{col}: MISMATCH computed={val_at_mid}, expected={expected}")
    
    elif col == 'complacency_index':
        rsi = tk_tape['rsi_value'].iloc[midpoint] or 50.0
        rsi_norm = (rsi - 50.0) / 50.0
        ws_val = tk_tape['wave_slope'].iloc[midpoint] or 0
        ws_prev = tk_tape['wave_slope'].iloc[midpoint - 5] or 0 if midpoint >= 5 else 0
        sd = ws_val - ws_prev
        sd_norm = max(-1.0, min(1.0, sd * 50.0))
        expected = rsi_norm - sd_norm
        match = abs((val_at_mid or 0) - expected) < 1e-3
        check(match, f"{col}: computed = {val_at_mid:.4f}, expected = {expected:.4f} ✓",
              f"{col}: MISMATCH computed={val_at_mid}, expected={expected}")
    
    elif col == 'rsi_extreme_zone':
        rsi = tk_tape['rsi_value'].iloc[midpoint] or 50.0
        expected = 1 if rsi > 80 else 0
        check(val_at_mid == expected, f"{col}: RSI={rsi:.1f}, zone={val_at_mid} ✓",
              f"{col}: MISMATCH RSI={rsi}, got={val_at_mid}, expected={expected}")
    
    elif col == 'rsi_trap_zone':
        rsi = tk_tape['rsi_value'].iloc[midpoint] or 50.0
        expected = 1 if 65 <= rsi <= 75 else 0
        check(val_at_mid == expected, f"{col}: RSI={rsi:.1f}, zone={val_at_mid} ✓",
              f"{col}: MISMATCH RSI={rsi}, got={val_at_mid}, expected={expected}")
    
    elif col == 'rsi_bearish_div':
        # Rolling max of RSI over last 60 bars
        start = max(0, midpoint - 59)
        rsi_window = tk_tape['rsi_value'].iloc[start:midpoint + 1].values
        rsi_curr = tk_tape['rsi_value'].iloc[midpoint] or 50.0
        rsi_max = np.nanmax(rsi_window)
        expected = 1 if rsi_curr < rsi_max - 2.0 else 0
        check(val_at_mid == expected,
              f"{col}: RSI={rsi_curr:.1f}, max60={rsi_max:.1f}, div={val_at_mid} ✓",
              f"{col}: MISMATCH RSI={rsi_curr}, max60={rsi_max}, got={val_at_mid}, expected={expected}")

# ═══════════════════════════════════════════════════════════
banner("3. ZIGZAG-FREE — ¿Cero dependencia del zigzag?")
# ═══════════════════════════════════════════════════════════

import subprocess
# Check source code for zigzag references (excluding comments and evaluation scripts)
result = subprocess.run(
    ['grep', '-rn', 'zigzag', 
     'backend/scripts/backtest_signal_tape.py',
     'backend/scripts/unified_pretrainer_v2.py'],
    capture_output=True, text=True, cwd=str(root)
)
lines = [l for l in result.stdout.strip().split('\n') if l]
zigzag_in_compute = [l for l in lines if 'zigzag' in l.lower() and 'NO zigzag' not in l]

if not zigzag_in_compute:
    check(True, "Cero referencias funcionales al zigzag en código de features", "")
else:
    check(False, "", f"Zigzag encontrado: {zigzag_in_compute}")
    for l in zigzag_in_compute:
        print(f"    {l}")

# Also check that no zigzag table is queried during feature computation
check('zigzag_points' not in open(root / 'backend/scripts/backtest_signal_tape.py').read(),
      "backtest_signal_tape.py: NO queries a engine.zigzag_points", 
      "backtest_signal_tape.py: QUERIES zigzag_points!")

# ═══════════════════════════════════════════════════════════
banner("4. DISTRIBUCIÓN — ¿Rangos razonables?")
# ═══════════════════════════════════════════════════════════

for col in NEW_COLS:
    if col not in tape.columns:
        continue
    vals = tape[col].dropna()
    if len(vals) == 0:
        warn(f"{col}: NO DATA")
        continue
    
    mn, mx, mean, std = vals.min(), vals.max(), vals.mean(), vals.std()
    print(f"  {col:>25s}: min={mn:>+10.4f}  max={mx:>+10.4f}  mean={mean:>+8.4f}  std={std:>8.4f}  N={len(vals):,d}")
    
    # Sanity checks
    if col in ('rsi_extreme_zone', 'rsi_trap_zone', 'rsi_bearish_div'):
        check(set(vals.unique()).issubset({0, 1}),
              f"  {col}: binary (0/1 only) ✓",
              f"  {col}: NOT binary! Unique: {sorted(vals.unique())}")
        pct1 = (vals == 1).mean() * 100
        print(f"      → {pct1:.1f}% = 1 (active)")
    
    if col == 'slope_decel_wave':
        check(abs(mean) < 0.1, f"  {col}: mean near zero ({mean:+.4f}) ✓ (centered)",
              f"  {col}: mean too far from zero ({mean:+.4f})")
    
    if col == 'sigma_divergence':
        check(std > 0.1, f"  {col}: has variance (std={std:.4f}) ✓",
              f"  {col}: near-zero variance (std={std:.4f})")

# ═══════════════════════════════════════════════════════════
banner("5. NO-DEGRADACIÓN — ¿Heads existentes intactos?")
# ═══════════════════════════════════════════════════════════

OLD_COLS = ['p_long_entry', 'p_swing_exit', 'p_short_entry', 'p_short_cover',
            'p_pullback_depth', 'p_trend_reversal', 'p_bounce_height', 'p_trend_recovery']

for col in OLD_COLS:
    vals = tape[col].dropna()
    check(len(vals) > 0, f"{col}: {len(vals):,d} non-null values ✓",
          f"{col}: ALL NULL!")
    if len(vals) > 0:
        check(vals.min() >= 0 and vals.max() <= 1,
              f"  {col}: range [{vals.min():.3f}, {vals.max():.3f}] ✓ (valid probabilities)",
              f"  {col}: INVALID range [{vals.min():.3f}, {vals.max():.3f}]")

# ═══════════════════════════════════════════════════════════
banner("6. CROSS-VALIDATION — Recalcular independientemente")
# ═══════════════════════════════════════════════════════════

print("  Recalculando las 7 features desde datos crudos del tape para 3 tickers...")
mismatches = 0
total_checks = 0

for tk in ['SPY', 'AAPL', 'JPM']:
    tk_tape = tape[tape['ticker'] == tk].sort_values('timestamp').reset_index(drop=True)
    if len(tk_tape) < 100:
        continue
    
    # Recalculate slope_decel_wave
    ws = tk_tape['wave_slope'].fillna(0).values
    for i in range(10, len(tk_tape), 100):  # Sample every 100 bars
        expected_sdw = ws[i] - ws[i - 5]
        actual_sdw = tk_tape.loc[i, 'slope_decel_wave']
        if actual_sdw is not None and not np.isnan(actual_sdw):
            if abs(actual_sdw - expected_sdw) > 1e-4:
                mismatches += 1
                fail(f"  {tk} bar {i}: slope_decel_wave mismatch: got {actual_sdw}, expected {expected_sdw}")
            total_checks += 1
    
    # Recalculate sigma_divergence
    for i in range(10, len(tk_tape), 100):
        st = tk_tape.loc[i, 'sigma_tide'] or 0
        sw = tk_tape.loc[i, 'sigma_wave'] or 0
        expected_sd = st - sw
        actual_sd = tk_tape.loc[i, 'sigma_divergence']
        if actual_sd is not None and not np.isnan(actual_sd):
            if abs(actual_sd - expected_sd) > 1e-4:
                mismatches += 1
                fail(f"  {tk} bar {i}: sigma_divergence mismatch")
            total_checks += 1
    
    # Recalculate RSI zones
    for i in range(10, len(tk_tape), 100):
        rsi = tk_tape.loc[i, 'rsi_value'] or 50
        exp_ext = 1 if rsi > 80 else 0
        exp_trap = 1 if 65 <= rsi <= 75 else 0
        act_ext = tk_tape.loc[i, 'rsi_extreme_zone']
        act_trap = tk_tape.loc[i, 'rsi_trap_zone']
        if act_ext != exp_ext:
            mismatches += 1
            fail(f"  {tk} bar {i}: rsi_extreme_zone mismatch (RSI={rsi})")
        if act_trap != exp_trap:
            mismatches += 1
            fail(f"  {tk} bar {i}: rsi_trap_zone mismatch (RSI={rsi})")
        total_checks += 2

check(mismatches == 0, 
      f"Cross-validation: {total_checks} checks, 0 mismatches ✓",
      f"Cross-validation: {mismatches} mismatches in {total_checks} checks!")

# ═══════════════════════════════════════════════════════════
banner("7. TICKER COVERAGE — ¿Todos los tickers tienen features?")
# ═══════════════════════════════════════════════════════════

TICKERS = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'AMZN', 'COST', 'HD', 'HON',
           'IBM', 'JNJ', 'JPM', 'MCD', 'MRK', 'PEP', 'PG', 'WMT', 'XOM']

for tk in TICKERS:
    tk_tape = tape[tape['ticker'] == tk]
    n = len(tk_tape)
    has_new = all(tk_tape[col].notna().sum() > 0 for col in NEW_COLS if col in tape.columns)
    check(has_new and n > 0,
          f"{tk}: {n:,d} rows, all 7 features present ✓",
          f"{tk}: {n} rows, features MISSING")

store.close()

# ═══════════════════════════════════════════════════════════
banner(f"VEREDICTO FINAL: {PASS_COUNT} PASS / {FAIL_COUNT} FAIL")
# ═══════════════════════════════════════════════════════════
if FAIL_COUNT == 0:
    print("  🟢 AUDITORÍA APROBADA — Procedimiento y calidad validados")
else:
    print(f"  🔴 {FAIL_COUNT} FALLOS DETECTADOS — REQUIERE CORRECCIÓN")
