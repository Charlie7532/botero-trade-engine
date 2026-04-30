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

echo "$(date): Botero Trade Monitors starting..."

# 1. Quality Daemon (Daily)
nohup python backend/application/quality_daemon.py --loop 86400 > backend/quality_daemon.log 2>&1 &
echo "Quality Daemon started."

# 2. Speculative Daemon (5 minutes)
nohup python backend/application/speculative_daemon.py --loop 300 > backend/speculative_daemon.log 2>&1 &
echo "Speculative Daemon started."

# 3. Position Monitor (5 minutes) - Continues tracking open positions
nohup python backend/application/position_monitor.py --loop 300 > backend/position_monitor.log 2>&1 &
echo "Position Monitor started."

echo "All daemons running in background."
