#!/usr/bin/env python3
"""
SPY ZigZag 2.5% Chart — Last Year
"""
import os, sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

OUTPUT = Path("/root/.gemini/antigravity-ide/brain/5fc2ba22-c7cc-498a-a09e-273483888ebd/spy_zigzag_25pct.png")

def main():
    store = TimescaleDataStore()

    # Load SPY last year
    ohlcv = store.load_bars("SPY", "1d")
    spy = ohlcv.copy()
    spy.index = spy.index.tz_localize(None) if spy.index.tz else spy.index
    cutoff = spy.index[-1] - pd.Timedelta(days=365)
    spy = spy[spy.index >= cutoff]

    # Load zigzag 2.5%
    zz = pd.read_sql(
        "SELECT timestamp, tp_type, price FROM engine.zigzag_points "
        "WHERE ticker='SPY' AND min_swing_pct=0.025 ORDER BY timestamp",
        store.engine
    )
    zz["timestamp"] = pd.to_datetime(zz["timestamp"]).dt.tz_localize(None)
    zz_last = zz[zz["timestamp"] >= cutoff]
    store.close()

    mins = zz_last[zz_last["tp_type"] == "MIN"]
    maxs = zz_last[zz_last["tp_type"] == "MAX"]

    # Build zigzag line (ordered by timestamp)
    zz_line = zz_last.sort_values("timestamp")

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')

    # Candlestick-style close line with fill
    dates = spy.index
    close = spy["close"].values
    high = spy["high"].values
    low = spy["low"].values

    # Price area
    ax.fill_between(dates, low, high, alpha=0.15, color='#4cc9f0', linewidth=0)
    ax.plot(dates, close, color='#4cc9f0', linewidth=1.2, alpha=0.8, label='SPY Close')

    # ZigZag line
    if not zz_line.empty:
        ax.plot(zz_line["timestamp"], zz_line["price"],
                color='#f72585', linewidth=2.0, alpha=0.9, zorder=5,
                label='ZigZag 2.5% (canonical H/L)')

    # MIN points (green triangles up)
    if not mins.empty:
        ax.scatter(mins["timestamp"], mins["price"],
                   color='#00ff88', marker='^', s=120, zorder=10,
                   edgecolors='white', linewidth=0.8, label=f'MIN ({len(mins)})')

    # MAX points (red triangles down)
    if not maxs.empty:
        ax.scatter(maxs["timestamp"], maxs["price"],
                   color='#ff4444', marker='v', s=120, zorder=10,
                   edgecolors='white', linewidth=0.8, label=f'MAX ({len(maxs)})')

    # Annotate swings
    for _, row in zz_line.iterrows():
        offset = 4 if row["tp_type"] == "MAX" else -4
        color = '#ff4444' if row["tp_type"] == "MAX" else '#00ff88'
        ax.annotate(f'${row["price"]:.0f}',
                    xy=(row["timestamp"], row["price"]),
                    xytext=(0, offset * 2.5),
                    textcoords='offset points',
                    fontsize=7, color=color, alpha=0.85,
                    ha='center', va='bottom' if row["tp_type"] == "MIN" else 'top')

    # Styling
    ax.set_title('SPY — ZigZag 2.5% Canonical (High/Low) — Last 12 Months',
                 fontsize=16, fontweight='bold', color='white', pad=15)
    ax.set_ylabel('Price ($)', fontsize=12, color='white')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha='right')

    ax.tick_params(colors='#aaaaaa')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#333333')
    ax.spines['left'].set_color('#333333')
    ax.grid(True, alpha=0.15, color='#555555')

    legend = ax.legend(loc='upper left', fontsize=10,
                       facecolor='#16213e', edgecolor='#333333',
                       labelcolor='white')

    # Stats box
    n_turns = len(zz_last)
    avg_days = zz_last.groupby("tp_type").apply(
        lambda g: g["timestamp"].diff().dt.days.median()
    )
    stats_text = (f"Turns: {n_turns} ({len(mins)} MIN + {len(maxs)} MAX)\n"
                  f"Avg swing: ~{(spy['close'].max() - spy['close'].min()) / max(n_turns, 1):.0f}pt per leg")
    ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
            fontsize=9, color='#aaaaaa', ha='right', va='bottom',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#1a1a2e', alpha=0.8, edgecolor='#333333'))

    plt.tight_layout()
    fig.savefig(OUTPUT, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {OUTPUT}")
    print(f"SPY last year: {len(spy)} bars, {len(zz_last)} zigzag points")

if __name__ == "__main__":
    main()
