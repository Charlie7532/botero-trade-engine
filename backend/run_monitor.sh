#!/bin/bash
# Botero Trade Position Monitor — Persistent
# Ejecutar con: nohup bash backend/run_monitor.sh &
# O con screen: screen -S monitor bash backend/run_monitor.sh

set -e
cd /root/botero-trade
source backend/.venv/bin/activate

export ALPACA_API_KEY=PKLBZC43ERHDNVTT4LEMM5ICJV
export ALPACA_SECRET_KEY=164GZfKpnLscLmsn4CCn31eP7XqVJ8iZPYQ25sQrr92
export FINNHUB_API_KEY=d7gffopr01qmqj4553cgd7gffopr01qmqj4553d0

echo "$(date): Botero Trade Monitor starting..."
python backend/application/position_monitor.py --loop 300  # Cada 5 minutos
