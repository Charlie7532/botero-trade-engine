#!/usr/bin/env python3
"""Audit zigzag data quality: alternation violations, nestedness, causal stereotypes."""
import os, sys
sys.path.insert(0, "/root/botero-trade")
from dotenv import load_dotenv
load_dotenv("/root/botero-trade/.env")
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
conn = store._conn()
cur = conn.cursor()

# ── 1. Show SPY alternation violations ──
cur.execute("""
    SELECT timestamp::date, tp_type, price, swing_return, swing_days
    FROM engine.zigzag_points 
    WHERE ticker = 'SPY' AND min_swing_pct = 0.025 
    ORDER BY timestamp
""")
rows = cur.fetchall()
print("=== SPY 2.5%% Alternation Violations ===")
violations_shown = 0
for i in range(1, len(rows)):
    if rows[i][1] == rows[i-1][1]:
        violations_shown += 1
        print(f"  [{i-1}] {rows[i-1][0]} {rows[i-1][1]} ${rows[i-1][2]:.2f}  swing_ret={rows[i-1][3]*100:.1f}%  days={rows[i-1][4]}")
        print(f"  [{i}]   {rows[i][0]} {rows[i][1]} ${rows[i][2]:.2f}  swing_ret={rows[i][3]*100:.1f}%  days={rows[i][4]}")
        print()
        if violations_shown >= 5:
            print("  ... (showing first 5)")
            break

# ── 2. Global alternation violations ──
cur.execute("""
    WITH ordered AS (
        SELECT ticker, tp_type, 
               LAG(tp_type) OVER (PARTITION BY ticker, min_swing_pct ORDER BY timestamp) as prev_tp
        FROM engine.zigzag_points
        WHERE min_swing_pct = 0.025
    )
    SELECT count(*) as violations
    FROM ordered WHERE tp_type = prev_tp
""")
v = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM engine.zigzag_points WHERE min_swing_pct = 0.025")
total = cur.fetchone()[0]
print(f"\n=== Global alternation violations (2.5%% level) ===")
print(f"  Total pivots: {total:,}")
print(f"  Violations: {v:,} ({v/total*100:.2f}%%)")

# ── 3. Causal stereotype demonstration on SPY ──
cur.execute("""
    SELECT timestamp::date, tp_type, price
    FROM engine.zigzag_points 
    WHERE ticker = 'SPY' AND min_swing_pct = 0.025 
    ORDER BY timestamp
    LIMIT 30
""")
pivots = cur.fetchall()

print(f"\n=== Causal Stereotype Derivation (SPY 2.5%%, first 30 pivots) ===")
print(f"{'#':>3} {'Date':>12} {'Type':>4} {'Price':>8} {'Zig':>4} {'Zag':>4} {'Stereo Before':>15} {'Stereo After':>14} {'Transition':>12}")
print("-" * 85)

last_zig = None
last_zag = None
prev_max_price = None
prev_min_price = None

for i, (dt, tp, price) in enumerate(pivots):
    stereo_before = (last_zig or "?") + (last_zag or "?")
    
    if tp == "MAX":
        if prev_max_price is not None:
            last_zig = "H" if price > prev_max_price else "L"
        prev_max_price = price
    else:  # MIN
        if prev_min_price is not None:
            last_zag = "H" if price > prev_min_price else "L"
        prev_min_price = price
    
    stereo_after = (last_zig or "?") + (last_zag or "?")
    
    changed = stereo_before != stereo_after and "?" not in stereo_before and "?" not in stereo_after
    transition = f"{stereo_before} -> {stereo_after}" if changed else "---"
    
    print(f"{i:3d} {dt!s:>12} {tp:>4} {price:8.2f} {last_zig or '?':>4} {last_zag or '?':>4} {stereo_before:>15} {stereo_after:>14} {transition:>12}")

# ── 4. Stereotype transition counts for SPY ──
cur.execute("""
    SELECT timestamp::date, tp_type, price
    FROM engine.zigzag_points 
    WHERE ticker = 'SPY' AND min_swing_pct = 0.025 
    ORDER BY timestamp
""")
all_pivots = cur.fetchall()

last_zig = None
last_zag = None
prev_max_price = None
prev_min_price = None

transitions_min = {}  # before -> after at MIN pivots
transitions_max = {}  # before -> after at MAX pivots

for dt, tp, price in all_pivots:
    stereo_before = (last_zig or "?") + (last_zag or "?")
    
    if tp == "MAX":
        if prev_max_price is not None:
            last_zig = "H" if price > prev_max_price else "L"
        prev_max_price = price
    else:
        if prev_min_price is not None:
            last_zag = "H" if price > prev_min_price else "L"
        prev_min_price = price
    
    stereo_after = (last_zig or "?") + (last_zag or "?")
    
    if "?" in stereo_before or "?" in stereo_after:
        continue
    
    key = f"{stereo_before}->{stereo_after}"
    if tp == "MIN":
        transitions_min[key] = transitions_min.get(key, 0) + 1
    else:
        transitions_max[key] = transitions_max.get(key, 0) + 1

print(f"\n=== Causal Stereotype Transitions at MIN Pivots (SPY) ===")
total_min = sum(transitions_min.values())
for k, v in sorted(transitions_min.items(), key=lambda x: -x[1]):
    print(f"  {k:10s}  {v:5d}  ({v/total_min*100:5.1f}%%)")

print(f"\n=== Causal Stereotype Transitions at MAX Pivots (SPY) ===")
total_max = sum(transitions_max.values())
for k, v in sorted(transitions_max.items(), key=lambda x: -x[1]):
    print(f"  {k:10s}  {v:5d}  ({v/total_max*100:5.1f}%%)")

store._put(conn)
store.close()
