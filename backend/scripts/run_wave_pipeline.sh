#!/bin/bash
# Run Wave table training pipeline in background
# Step 1: Train raw table (~5-10 min)
# Step 2: Generate derived table (~5 sec)

set -e

export PYTHONPATH=/root/botero-trade

echo "=========================================="
echo "  WAVE TABLE PIPELINE — $(date)"
echo "=========================================="

echo ""
echo "Step 1: Training rc_wave_probability_table.json..."
echo ""
/root/botero-trade/backend/.venv/bin/python /root/botero-trade/backend/scripts/train_wave_table.py

echo ""
echo "Step 2: Generating rc_wave_derived.json..."
echo ""
/root/botero-trade/backend/.venv/bin/python /root/botero-trade/backend/scripts/generate_wave_derived_table.py

echo ""
echo "=========================================="
echo "  PIPELINE COMPLETE — $(date)"
echo "=========================================="
