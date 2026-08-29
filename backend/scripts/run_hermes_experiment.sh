#!/usr/bin/env bash
# ==============================================================================
# backend/scripts/run_hermes_experiment.sh — Pipeline de Enlace Antigravity-Hermes
# ==============================================================================
# Orquesta el ciclo completo de investigación:
#   1. Ejecuta al Worker (Qwen) en un Git Worktree aislado.
#   2. Corre el Gatekeeper determinista local (pre_audit.py, $0 costo).
#   3. Si pre_audit aprueba (exit 0), despacha al Auditor Epistemológico (Kimi-k3).
#   4. Si pre_audit falla (exit 1), aborta inmediatamente sin gastar tokens de Kimi.
#
# Uso:
#   ./backend/scripts/run_hermes_experiment.sh <ruta_al_prompt.md>
# ==============================================================================
set -e

PROMPT_FILE="$1"

if [ -z "$PROMPT_FILE" ] || [ ! -f "$PROMPT_FILE" ]; then
    echo "❌ Error: Debe especificar un archivo de prompt válido."
    echo "Uso: $0 .hermes/prompts/<nombre_prompt>.md"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
WORKTREE_DIR="/tmp/hermes_$RUN_ID"
mkdir -p "$WORKTREE_DIR/artifacts"

echo "========================================================================"
echo "🚀 [1/3] Lanzando Worker en Worktree Aislado ($RUN_ID)..."
echo "========================================================================"

# Invocación de Hermes en modo worktree aislado y one-shot
hermes -p worker -w "$WORKTREE_DIR" -z "$(cat "$PROMPT_FILE")"

BACKTEST_RESULTS="$WORKTREE_DIR/artifacts/backtest_results.json"
if [ ! -f "$BACKTEST_RESULTS" ]; then
    echo "❌ Error: El worker no generó '$BACKTEST_RESULTS'."
    exit 1
fi

echo ""
echo "========================================================================"
echo "⚖️ [2/3] Ejecutando Gatekeeper Determinista (hermes_gates/pre_audit.py)..."
echo "========================================================================"

PRE_AUDIT_SUMMARY="$WORKTREE_DIR/artifacts/pre_audit_summary.json"

set +e
python3 hermes_gates/pre_audit.py \
    --input "$BACKTEST_RESULTS" \
    --output "$PRE_AUDIT_SUMMARY"
GATE_EXIT_CODE=$?
set -e

if [ $GATE_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "🛑 [RECHAZADO POR GATEKEEPER] La matemática/esquema no cumplió los requisitos."
    echo "💰 Gasto de API en Auditor Kimi-k3: $0.00 (Aborto preventivo)."
    exit 1
fi

echo ""
echo "========================================================================"
echo "🧠 [3/3] Invocando Auditor Epistemológico (Kimi-k3)..."
echo "========================================================================"

AUDITOR_PROMPT="Audita el siguiente resumen matemático y emite la Confidence Card definitiva con veredicto [APROBADO / RECHAZADO / CUARENTENA]:

$(cat "$PRE_AUDIT_SUMMARY")"

hermes -p auditor -z "$AUDITOR_PROMPT"

echo ""
echo "✅ Pipeline completado exitosamente para $RUN_ID."
