#!/usr/bin/env python3
"""
PIPELINE COMPLETO: Auditoría + Re-training
=============================================
Ejecuta secuencialmente:
1. Auditoría de integridad (17 tickers × 5 barras × 37 campos)
2. Re-entrenamiento de 8 heads (si la auditoría pasa)

Un solo script, un solo proceso, cero colisiones.
"""
import subprocess, sys, os, time

ROOT = "/root/botero-trade"
PYTHON = f"{ROOT}/backend/.venv/bin/python"
ENV = {**os.environ, "PYTHONPATH": ROOT}

def run(desc, script):
    print(f"\n{'='*90}")
    print(f"  FASE: {desc}")
    print(f"{'='*90}")
    t0 = time.time()
    result = subprocess.run(
        [PYTHON, script],
        cwd=ROOT, env=ENV,
        capture_output=False,
    )
    elapsed = time.time() - t0
    print(f"\n  → {desc}: {'✅ PASSED' if result.returncode == 0 else '❌ FAILED'} ({elapsed:.1f}s)")
    return result.returncode

def main():
    print("=" * 90)
    print("  PIPELINE COMPLETO — Auditoría + Training")
    print("  Secuencial. Sin colisiones. Sin sorpresas.")
    print("=" * 90)

    # FASE 1: Auditoría
    code = run("AUDITORÍA 17 TICKERS", f"{ROOT}/backend/scripts/audit_vault_vs_compute.py")
    if code != 0:
        print("\n  ✖ AUDITORÍA FALLÓ — NO SE PROCEDE CON TRAINING")
        sys.exit(1)

    # FASE 2: Training
    code = run("RE-TRAINING 8 HEADS", f"{ROOT}/backend/scripts/unified_pretrainer_v2.py")
    if code != 0:
        print("\n  ✖ TRAINING FALLÓ")
        sys.exit(1)

    print(f"\n{'='*90}")
    print(f"  ★★★ PIPELINE COMPLETO ★★★")
    print(f"{'='*90}")

if __name__ == "__main__":
    main()
